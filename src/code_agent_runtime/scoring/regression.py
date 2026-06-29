"""Regression comparison and flakiness analysis (Milestone 9).

Two analyses over the :class:`~code_agent_runtime.scoring.SuiteResult` files that
:func:`~code_agent_runtime.scoring.run_suite` produces:

- **Regression comparison** (:func:`compare_suites`) diffs a *baseline* suite
  result against a *candidate* one, keyed by ``(task_id, agent)``, and buckets
  every key as **improved**, **regressed**, **unchanged**, **flaky**, **added**, or
  **removed**. The headline signal is the pass/fail boolean: *improved* means the
  candidate gained a pass it did not have; *regressed* means it lost one. Any
  other transition (e.g. ``failed → error``) is *unchanged* in pass/fail terms but
  its outcome change is recorded in ``detail``, so nothing is silently dropped.
- **Flakiness analysis** (:func:`analyze_flakiness`) consumes several repeats of
  the *same* suite (see :func:`~code_agent_runtime.scoring.run_repeated`) and flags
  any ``(task_id, agent)`` key whose verdict was not identical across the repeats.
  The deterministic mock/scripted/probe agents are flake-free by construction, so
  the baseline reports **zero** flaky keys — a property the tests assert and the
  analyser is built to surface, not to assume.

Both report types are pure data with JSON round-trips, so a comparison or a
flakiness verdict can be persisted and re-rendered (see
:mod:`code_agent_runtime.reports.regression`) without re-running anything.

This module imports only the scoring layer (never the runtime), so it stays a
layer below the runtime in the import graph, exactly like the rest of ``scoring``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scorer import Outcome
from .suite import EvalRecord, SuiteResult

#: Schema version for a persisted comparison/flakiness report (bumped on breaks).
REGRESSION_SCHEMA_VERSION = 1

# -- comparison category vocabulary -----------------------------------------

IMPROVED = "improved"
REGRESSED = "regressed"
UNCHANGED = "unchanged"
FLAKY = "flaky"
ADDED = "added"
REMOVED = "removed"

#: The categories a key can fall into, in report order.
CATEGORIES: tuple[str, ...] = (IMPROVED, REGRESSED, UNCHANGED, FLAKY, ADDED, REMOVED)


def _pass_status(passed: bool | None) -> str:
    """Collapse a tri-state ``passed`` to ``pass`` / ``fail`` / ``other``.

    ``other`` covers ``not_scored`` and ``error`` — runs that are neither a pass
    nor a fail, so they neither earn an *improved* nor an *regressed* verdict on
    their own.
    """
    if passed is True:
        return "pass"
    if passed is False:
        return "fail"
    return "other"


# -- collapsing repeated records into one representative per key -------------


@dataclass(frozen=True)
class CollapsedRun:
    """One side's view of a ``(task_id, agent)`` key after collapsing repeats.

    A normal suite result has exactly one record per key (``n_runs == 1``, never
    ``flaky``). A result built from repeats (e.g. via
    :func:`~code_agent_runtime.scoring.merge_suites`) may have several; ``flaky``
    is set when those repeats did not all agree on the outcome, and ``passed`` /
    ``outcome`` report the *latest* repeat as the representative.
    """

    task_id: str
    agent: str
    passed: bool | None
    outcome: str
    n_runs: int
    outcomes: tuple[str, ...]
    flaky: bool


def _collapse(suite: SuiteResult) -> dict[tuple[str, str], CollapsedRun]:
    """Group a suite's records by ``(task_id, agent)`` into one view per key."""
    groups: dict[tuple[str, str], list[EvalRecord]] = {}
    for rec in suite.records:
        groups.setdefault((rec.task_id, rec.agent), []).append(rec)
    view: dict[tuple[str, str], CollapsedRun] = {}
    for key, recs in groups.items():
        outcomes = tuple(r.outcome for r in recs)
        last = recs[-1]
        view[key] = CollapsedRun(
            task_id=key[0],
            agent=key[1],
            passed=last.passed,
            outcome=last.outcome,
            n_runs=len(recs),
            outcomes=outcomes,
            flaky=len(set(outcomes)) > 1,
        )
    return view


# -- regression comparison --------------------------------------------------


@dataclass(frozen=True)
class RegressionEntry:
    """One ``(task_id, agent)`` key's verdict in a comparison."""

    task_id: str
    agent: str
    category: str
    baseline_outcome: str | None
    candidate_outcome: str | None
    baseline_passed: bool | None
    candidate_passed: bool | None
    detail: str
    baseline_flaky: bool = False
    candidate_flaky: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "category": self.category,
            "baseline_outcome": self.baseline_outcome,
            "candidate_outcome": self.candidate_outcome,
            "baseline_passed": self.baseline_passed,
            "candidate_passed": self.candidate_passed,
            "detail": self.detail,
            "baseline_flaky": self.baseline_flaky,
            "candidate_flaky": self.candidate_flaky,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RegressionEntry":
        return cls(
            task_id=data["task_id"],
            agent=data["agent"],
            category=data["category"],
            baseline_outcome=data.get("baseline_outcome"),
            candidate_outcome=data.get("candidate_outcome"),
            baseline_passed=data.get("baseline_passed"),
            candidate_passed=data.get("candidate_passed"),
            detail=data.get("detail", ""),
            baseline_flaky=bool(data.get("baseline_flaky", False)),
            candidate_flaky=bool(data.get("candidate_flaky", False)),
        )


def _classify(base: CollapsedRun, cand: CollapsedRun) -> tuple[str, str]:
    """Bucket a key that exists on both sides, returning ``(category, detail)``.

    A flake on either side wins (the flip cannot be trusted as a real change).
    Otherwise the pass/fail boolean drives the verdict: gaining a pass is
    *improved*, losing one is *regressed*; everything else is *unchanged* with the
    outcome transition noted when the outcome (but not the pass/fail signal)
    changed.
    """
    if base.flaky or cand.flaky:
        return FLAKY, "non-deterministic outcome across repeats"
    transition = f"{base.outcome} → {cand.outcome}"
    bs, cs = _pass_status(base.passed), _pass_status(cand.passed)
    if bs != "pass" and cs == "pass":
        return IMPROVED, transition
    if bs == "pass" and cs != "pass":
        return REGRESSED, transition
    if base.outcome != cand.outcome:
        return UNCHANGED, f"{transition} (no pass/fail change)"
    return UNCHANGED, base.outcome


@dataclass(frozen=True)
class RegressionComparison:
    """A baseline-vs-candidate comparison: one :class:`RegressionEntry` per key."""

    entries: tuple[RegressionEntry, ...]
    baseline_label: str | None = None
    candidate_label: str | None = None
    schema_version: int = REGRESSION_SCHEMA_VERSION

    def by_category(self, category: str) -> tuple[RegressionEntry, ...]:
        return tuple(e for e in self.entries if e.category == category)

    @property
    def improved(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(IMPROVED)

    @property
    def regressed(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(REGRESSED)

    @property
    def unchanged(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(UNCHANGED)

    @property
    def flaky(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(FLAKY)

    @property
    def added(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(ADDED)

    @property
    def removed(self) -> tuple[RegressionEntry, ...]:
        return self.by_category(REMOVED)

    def counts(self) -> dict[str, int]:
        """Count entries per category (every category present, zero-filled)."""
        counts = {c: 0 for c in CATEGORIES}
        for e in self.entries:
            counts[e.category] = counts.get(e.category, 0) + 1
        return counts

    @property
    def has_regressions(self) -> bool:
        """True iff any key regressed — the natural CI gate."""
        return any(e.category == REGRESSED for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "baseline_label": self.baseline_label,
            "candidate_label": self.candidate_label,
            "counts": self.counts(),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RegressionComparison":
        return cls(
            entries=tuple(RegressionEntry.from_dict(e) for e in data.get("entries", [])),
            baseline_label=data.get("baseline_label"),
            candidate_label=data.get("candidate_label"),
            schema_version=int(data.get("schema_version", REGRESSION_SCHEMA_VERSION)),
        )


def compare_suites(baseline: SuiteResult, candidate: SuiteResult) -> RegressionComparison:
    """Compare two suite results, bucketing every ``(task_id, agent)`` key.

    Keys present on only one side are ``added`` (candidate-only) or ``removed``
    (baseline-only). Keys on both sides are classified by :func:`_classify`. Either
    input may contain repeated records per key (a merged rerun result), in which
    case a key that flipped within a side is reported ``flaky``.
    """
    bview = _collapse(baseline)
    cview = _collapse(candidate)
    entries: list[RegressionEntry] = []
    for key in sorted(set(bview) | set(cview)):
        base = bview.get(key)
        cand = cview.get(key)
        if base is None:
            assert cand is not None
            entries.append(
                RegressionEntry(
                    task_id=key[0],
                    agent=key[1],
                    category=ADDED,
                    baseline_outcome=None,
                    candidate_outcome=cand.outcome,
                    baseline_passed=None,
                    candidate_passed=cand.passed,
                    detail=f"new run: {cand.outcome}",
                    candidate_flaky=cand.flaky,
                )
            )
            continue
        if cand is None:
            entries.append(
                RegressionEntry(
                    task_id=key[0],
                    agent=key[1],
                    category=REMOVED,
                    baseline_outcome=base.outcome,
                    candidate_outcome=None,
                    baseline_passed=base.passed,
                    candidate_passed=None,
                    detail=f"dropped run: {base.outcome}",
                    baseline_flaky=base.flaky,
                )
            )
            continue
        category, detail = _classify(base, cand)
        entries.append(
            RegressionEntry(
                task_id=key[0],
                agent=key[1],
                category=category,
                baseline_outcome=base.outcome,
                candidate_outcome=cand.outcome,
                baseline_passed=base.passed,
                candidate_passed=cand.passed,
                detail=detail,
                baseline_flaky=base.flaky,
                candidate_flaky=cand.flaky,
            )
        )
    return RegressionComparison(
        entries=tuple(entries),
        baseline_label=baseline.label,
        candidate_label=candidate.label,
    )


# -- flakiness analysis -----------------------------------------------------


@dataclass(frozen=True)
class FlakinessEntry:
    """Flakiness stats for one ``(task_id, agent)`` key across N repeats."""

    task_id: str
    agent: str
    runs: int
    outcomes: tuple[str, ...]
    pass_count: int
    fail_count: int
    flaky: bool
    #: True iff a deterministic effort signal (tool/command count) varied across
    #: repeats even though the *verdict* may not have. Reported, not counted as a
    #: flake — a verdict-stable but path-varying agent is informative, not broken.
    signal_varied: bool = False

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.runs if self.runs else 0.0

    @property
    def distinct_outcomes(self) -> tuple[str, ...]:
        # Preserve first-seen order so the report is stable across runs.
        seen: list[str] = []
        for o in self.outcomes:
            if o not in seen:
                seen.append(o)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "runs": self.runs,
            "outcomes": list(self.outcomes),
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "flaky": self.flaky,
            "signal_varied": self.signal_varied,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlakinessEntry":
        return cls(
            task_id=data["task_id"],
            agent=data["agent"],
            runs=int(data["runs"]),
            outcomes=tuple(data.get("outcomes", [])),
            pass_count=int(data.get("pass_count", 0)),
            fail_count=int(data.get("fail_count", 0)),
            flaky=bool(data.get("flaky", False)),
            signal_varied=bool(data.get("signal_varied", False)),
        )


@dataclass(frozen=True)
class FlakinessReport:
    """The flakiness verdict over a set of repeated suite runs."""

    entries: tuple[FlakinessEntry, ...]
    runs: int
    label: str | None = None
    schema_version: int = REGRESSION_SCHEMA_VERSION

    @property
    def flaky(self) -> tuple[FlakinessEntry, ...]:
        return tuple(e for e in self.entries if e.flaky)

    @property
    def stable(self) -> tuple[FlakinessEntry, ...]:
        return tuple(e for e in self.entries if not e.flaky)

    @property
    def has_flakes(self) -> bool:
        return any(e.flaky for e in self.entries)

    def counts(self) -> dict[str, int]:
        return {
            "keys": len(self.entries),
            "flaky": len(self.flaky),
            "stable": len(self.stable),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "label": self.label,
            "runs": self.runs,
            "counts": self.counts(),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlakinessReport":
        return cls(
            entries=tuple(FlakinessEntry.from_dict(e) for e in data.get("entries", [])),
            runs=int(data.get("runs", 0)),
            label=data.get("label"),
            schema_version=int(data.get("schema_version", REGRESSION_SCHEMA_VERSION)),
        )


def analyze_flakiness(
    suites: Sequence[SuiteResult], *, label: str | None = None
) -> FlakinessReport:
    """Aggregate repeated runs of one suite into a per-key flakiness verdict.

    ``suites`` is the list of repeats (e.g. from
    :func:`~code_agent_runtime.scoring.run_repeated`). For each
    ``(task_id, agent)`` key the analyser collects the outcome of every repeat; a
    key is **flaky** iff those outcomes were not all identical. Verdict flakiness
    is judged on the scored outcome only — wall-clock runtime is excluded as noise,
    while tool/command-count variation is reported as ``signal_varied`` without
    counting as a flake.
    """
    groups: dict[tuple[str, str], list[EvalRecord]] = {}
    for suite in suites:
        for rec in suite.records:
            groups.setdefault((rec.task_id, rec.agent), []).append(rec)

    entries: list[FlakinessEntry] = []
    for key in sorted(groups):
        recs = groups[key]
        outcomes = tuple(r.outcome for r in recs)
        signals = {(r.tool_call_count, r.command_count, r.blocked_count) for r in recs}
        entries.append(
            FlakinessEntry(
                task_id=key[0],
                agent=key[1],
                runs=len(recs),
                outcomes=outcomes,
                pass_count=sum(1 for r in recs if r.passed is True),
                fail_count=sum(1 for r in recs if r.passed is False),
                flaky=len(set(outcomes)) > 1,
                signal_varied=len(signals) > 1,
            )
        )
    return FlakinessReport(entries=tuple(entries), runs=len(suites), label=label)


# -- persistence ------------------------------------------------------------


def write_comparison(comparison: RegressionComparison, path: str | Path) -> Path:
    """Write a comparison to ``path`` as JSON (creating parent directories)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(comparison.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def load_comparison(path: str | Path) -> RegressionComparison:
    """Load a comparison previously written by :func:`write_comparison`."""
    return RegressionComparison.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def write_flakiness(report: FlakinessReport, path: str | Path) -> Path:
    """Write a flakiness report to ``path`` as JSON (creating parent directories)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def load_flakiness(path: str | Path) -> FlakinessReport:
    """Load a flakiness report previously written by :func:`write_flakiness`."""
    return FlakinessReport.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
