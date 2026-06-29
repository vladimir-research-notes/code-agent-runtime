"""Scoring core: turn a finished run into a pass/fail verdict (Milestone 8).

A *scorer* answers one question about a completed run: did it pass? The four
methods the task schema names each answer it differently:

- ``test_command`` — pass iff the task's test command exited zero;
- ``expected_files`` — pass iff named files exist / are absent / contain text;
- ``diff_constraint`` — pass iff the change stayed within a declared file scope;
- ``custom`` — pass per a named scorer in the custom-scorer registry;
- ``none`` — not automatically scored.

This module owns the shared vocabulary — :class:`ScoreInput` (what a scorer is
given), :class:`ScoreVerdict` (what it returns), :class:`CheckResult` (one named
sub-check), and the small constructor helpers — plus the :func:`score_run`
dispatcher. The per-method scorers live in sibling modules
(:mod:`.test_scorer`, :mod:`.diff_scorer`, :mod:`.expected_files`,
:mod:`.custom`); :func:`score_run` imports them lazily so this package stays a
layer *below* the runtime and never imports it back.

Design notes:

- **Scoring is a pure function of evidence.** A :class:`ScoreInput` carries only
  data the run already produced — the test result, the captured diff, and the
  live workspace path — so a verdict is reproducible and unit-testable without
  re-running anything.
- **The verdict is richer than a boolean.** Beyond ``outcome``/``passed`` it
  carries a human ``detail`` and a list of :class:`CheckResult` sub-checks, so a
  failure says *which* expectation broke, not merely that one did.
- **Outcome vocabulary mirrors the runtime.** :class:`Outcome`'s strings equal
  :class:`code_agent_runtime.runtime.state.RunOutcome`'s; a test asserts they
  agree, so the runtime can store ``verdict.to_dict()`` as its ``score`` and
  compare ``score['outcome']`` against ``RunOutcome`` constants unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..tasks import Task


class Outcome:
    """The scored verdict vocabulary.

    These string values intentionally mirror
    :class:`code_agent_runtime.runtime.state.RunOutcome`; keeping them defined
    here lets :mod:`scoring` stay below the runtime in the import graph. A test
    (`tests/test_scoring.py`) asserts the two sets are identical so they cannot
    drift.
    """

    PASSED = "passed"
    FAILED = "failed"
    NOT_SCORED = "not_scored"
    ERROR = "error"

    ALL = frozenset({PASSED, FAILED, NOT_SCORED, ERROR})


@dataclass(frozen=True)
class CheckResult:
    """One named sub-check contributing to a score (e.g. a single expected file)."""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class ScoreInput:
    """Everything a scorer may inspect about a finished run.

    All fields are plain data the runtime already produced. ``workspace`` is the
    run's live workspace directory *at scoring time* (before cleanup), so a
    filesystem-checking scorer (``expected_files``) can read it; it is ``None``
    when the directory is unavailable.
    """

    task: Task
    tests: Mapping[str, Any] | None = None
    diff: Mapping[str, Any] | None = None
    workspace: Path | None = None

    @property
    def config(self) -> Mapping[str, Any]:
        """The task's method-specific ``scoring_config`` (possibly empty)."""
        return self.task.scoring_config


@dataclass(frozen=True)
class ScoreVerdict:
    """The result of scoring one run: the verdict plus its supporting evidence."""

    method: str
    outcome: str
    passed: bool | None
    detail: str
    checks: tuple[CheckResult, ...] = ()
    #: Optional method-specific extras (e.g. the offending paths) for reports.
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the dict the runtime stores as ``RunResult.score``.

        The four keys ``method``/``outcome``/``passed``/``detail`` match the
        Milestone 4 score shape, so existing report/format code is unchanged;
        ``checks``/``extra`` are additive.
        """
        out: dict[str, Any] = {
            "method": self.method,
            "outcome": self.outcome,
            "passed": self.passed,
            "detail": self.detail,
        }
        if self.checks:
            out["checks"] = [c.to_dict() for c in self.checks]
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


#: A scorer takes the evidence and returns a verdict.
Scorer = Callable[[ScoreInput], ScoreVerdict]


# -- constructor helpers ----------------------------------------------------


def passed(method: str, detail: str, checks: tuple[CheckResult, ...] = (), **extra: Any) -> ScoreVerdict:
    return ScoreVerdict(method, Outcome.PASSED, True, detail, checks, dict(extra))


def failed(method: str, detail: str, checks: tuple[CheckResult, ...] = (), **extra: Any) -> ScoreVerdict:
    return ScoreVerdict(method, Outcome.FAILED, False, detail, checks, dict(extra))


def not_scored(method: str, detail: str, **extra: Any) -> ScoreVerdict:
    return ScoreVerdict(method, Outcome.NOT_SCORED, None, detail, (), dict(extra))


def errored(method: str, detail: str, **extra: Any) -> ScoreVerdict:
    return ScoreVerdict(method, Outcome.ERROR, None, detail, (), dict(extra))


def from_checks(method: str, checks: tuple[CheckResult, ...], *, all_label: str) -> ScoreVerdict:
    """Pass iff every check passed; ``detail`` summarises the pass/total count."""
    n_pass = sum(1 for c in checks if c.passed)
    detail = f"{n_pass}/{len(checks)} {all_label} satisfied"
    if n_pass == len(checks):
        return passed(method, detail, checks)
    failures = "; ".join(c.detail for c in checks if not c.passed)
    return failed(method, f"{detail} — {failures}", checks)


def score_none(_inp: ScoreInput) -> ScoreVerdict:
    """Scoring method ``none``: completed but not automatically judged."""
    return not_scored("none", "task is not automatically scored (scoring_method 'none')")


def _scorers() -> dict[str, Scorer]:
    """Build the method → scorer table (imported lazily to avoid import cycles)."""
    from .custom import score_custom
    from .diff_scorer import score_diff_constraint
    from .expected_files import score_expected_files
    from .test_scorer import score_test_command

    return {
        "test_command": score_test_command,
        "expected_files": score_expected_files,
        "diff_constraint": score_diff_constraint,
        "custom": score_custom,
        "none": score_none,
    }


def score_run(
    task: Task,
    *,
    tests: Mapping[str, Any] | None = None,
    diff: Mapping[str, Any] | None = None,
    workspace: str | Path | None = None,
) -> ScoreVerdict:
    """Score a finished run of ``task`` against its ``scoring_method``.

    ``tests`` is the ``run_tests`` result data, ``diff`` the ``git_diff`` data,
    and ``workspace`` the live workspace path (for filesystem checks). An
    unrecognised method yields a ``not_scored`` verdict rather than raising —
    though the task schema validates the method, so this is defensive.
    """
    inp = ScoreInput(
        task=task,
        tests=tests,
        diff=diff,
        workspace=Path(workspace) if workspace is not None else None,
    )
    scorer = _scorers().get(task.scoring_method)
    if scorer is None:  # pragma: no cover - schema restricts the method set
        return not_scored(task.scoring_method, f"no scorer for method {task.scoring_method!r}")
    return scorer(inp)
