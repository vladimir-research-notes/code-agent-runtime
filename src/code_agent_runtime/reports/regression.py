"""Markdown reports for regression comparison and flakiness (Milestone 9).

Renders the two Milestone 9 analyses as Markdown documents:

- :func:`regression_to_markdown` for a
  :class:`~code_agent_runtime.scoring.RegressionComparison` — a per-category
  summary line followed by one table per non-empty bucket (improved, regressed,
  unchanged, flaky, added, removed).
- :func:`flakiness_to_markdown` for a
  :class:`~code_agent_runtime.scoring.FlakinessReport` — a summary line and a
  per-key table of the outcomes observed across the repeats.

Both reuse the Markdown-cell sanitiser from the suite report so a stray pipe or
newline in a label can never break a table row. Like the rest of ``reports``,
this module imports the scoring layer but never the runtime.
"""

from __future__ import annotations

from ..scoring.regression import (
    ADDED,
    CATEGORIES,
    FLAKY,
    IMPROVED,
    REGRESSED,
    REMOVED,
    UNCHANGED,
    FlakinessReport,
    RegressionComparison,
    RegressionEntry,
)
from .markdown import _cell, _row

#: Human-readable heading per category, with a one-line gloss.
_CATEGORY_HEADINGS = {
    IMPROVED: "Improved (gained a pass)",
    REGRESSED: "Regressed (lost a pass)",
    UNCHANGED: "Unchanged",
    FLAKY: "Flaky (non-deterministic across repeats)",
    ADDED: "Added (only in candidate)",
    REMOVED: "Removed (only in baseline)",
}

_ENTRY_COLUMNS = ("task id", "agent", "baseline", "candidate", "detail")


def _outcome_cell(outcome: str | None) -> str:
    return outcome if outcome is not None else "—"


def _entry_row(entry: RegressionEntry) -> str:
    return _row(
        (
            entry.task_id,
            entry.agent,
            _outcome_cell(entry.baseline_outcome),
            _outcome_cell(entry.candidate_outcome),
            entry.detail,
        )
    )


def regression_to_markdown(
    comparison: RegressionComparison, *, title: str = "Regression comparison"
) -> str:
    """Render a :class:`RegressionComparison` as a Markdown report string."""
    counts = comparison.counts()
    lines: list[str] = [f"# {title}"]
    base = comparison.baseline_label or "baseline"
    cand = comparison.candidate_label or "candidate"
    lines.append(f"\n_baseline: {_cell(base)} → candidate: {_cell(cand)}_")
    lines.append(
        f"\n**{len(comparison.entries)} key(s)** — "
        f"{counts[IMPROVED]} improved, {counts[REGRESSED]} regressed, "
        f"{counts[UNCHANGED]} unchanged, {counts[FLAKY]} flaky, "
        f"{counts[ADDED]} added, {counts[REMOVED]} removed."
    )
    if comparison.has_regressions:
        lines.append(f"\n> ⚠ {counts[REGRESSED]} regression(s) — see below.")

    for category in CATEGORIES:
        entries = comparison.by_category(category)
        if not entries:
            continue
        lines.append("")
        lines.append(f"## {_CATEGORY_HEADINGS[category]} ({len(entries)})")
        lines.append(_row(_ENTRY_COLUMNS))
        lines.append("| " + " | ".join("---" for _ in _ENTRY_COLUMNS) + " |")
        lines += [_entry_row(e) for e in entries]

    lines.append("")
    lines.append("## Notes")
    lines.append(
        "- Keys are `(task id, agent)`. *Improved*/*regressed* are driven by the "
        "pass/fail signal: a key is improved only if it gained a pass and regressed "
        "only if it lost one."
    )
    lines.append(
        "- A `failed → error` (or similar) transition that neither gains nor loses a "
        "pass is reported `unchanged`, with the outcome change shown in `detail`."
    )
    lines.append(
        "- *Flaky* keys flipped outcome across repeats within one side; their "
        "improved/regressed status cannot be trusted and is reported separately."
    )
    return "\n".join(lines) + "\n"


_FLAKY_COLUMNS = ("task id", "agent", "runs", "pass", "fail", "outcomes", "flaky")


def flakiness_to_markdown(
    report: FlakinessReport, *, title: str = "Flakiness analysis"
) -> str:
    """Render a :class:`FlakinessReport` as a Markdown report string."""
    counts = report.counts()
    lines: list[str] = [f"# {title}"]
    if report.label:
        lines.append(f"\n_Suite: {_cell(report.label)}_")
    lines.append(
        f"\n**{report.runs} repeat(s)** over {counts['keys']} key(s) — "
        f"{counts['flaky']} flaky, {counts['stable']} stable."
    )
    if report.has_flakes:
        lines.append(f"\n> ⚠ {counts['flaky']} flaky key(s) — outcome varied across repeats.")
    else:
        lines.append("\n> No flaky keys: every key produced an identical verdict on every repeat.")

    lines.append("")
    lines.append(_row(_FLAKY_COLUMNS))
    lines.append("| " + " | ".join("---" for _ in _FLAKY_COLUMNS) + " |")
    for e in report.entries:
        outcomes = ", ".join(e.distinct_outcomes)
        flag = "**yes**" if e.flaky else "no"
        if not e.flaky and e.signal_varied:
            flag = "no (signal varied)"
        lines.append(
            _row(
                (
                    e.task_id,
                    e.agent,
                    e.runs,
                    e.pass_count,
                    e.fail_count,
                    outcomes,
                    flag,
                )
            )
        )

    lines.append("")
    lines.append("## Notes")
    lines.append(
        "- A key is *flaky* iff its scored outcome was not identical on every "
        "repeat. The deterministic mock/scripted/probe agents are flake-free by "
        "construction, so the baseline shows zero flaky keys."
    )
    lines.append(
        "- Verdict flakiness ignores wall-clock runtime (always noisy). A "
        "`signal varied` note means tool/command counts differed across repeats "
        "while the verdict did not — informative, not counted as a flake."
    )
    return "\n".join(lines) + "\n"
