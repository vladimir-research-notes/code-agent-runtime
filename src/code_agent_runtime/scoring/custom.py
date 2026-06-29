"""The ``custom`` scorer hook and its registry (Milestone 8).

A task with ``scoring_method: "custom"`` names a scorer in ``scoring_config.name``;
:func:`score_custom` looks it up in :data:`CUSTOM_SCORERS` and dispatches. This is
the extension point for scoring logic the four built-in methods do not cover —
notably *combining* them, since the built-in methods are deliberately atomic.

Scorers are registered **in code**, not loaded from a task file: a task only
selects a scorer by name and supplies parameters. That keeps scoring
deterministic and avoids importing task-specified code (a task is data, never an
import path). Register your own with :func:`register_custom_scorer`.

One scorer ships as a worked example: ``tests_pass_and_diff_scope`` — pass iff the
test command passed *and* the change stayed within ``scoring_config.allowed_paths``
— which is how you express "fix it, but only touch these files".
"""

from __future__ import annotations

from .diff_scorer import score_diff_constraint
from .scorer import CheckResult, ScoreInput, ScoreVerdict, errored, from_checks
from .test_scorer import score_test_command


def _tests_pass_and_diff_scope(inp: ScoreInput) -> ScoreVerdict:
    """Composite: the test command passed AND the diff stayed within scope.

    Combines the two built-in scorers directly, so it inherits their semantics:
    the scope half is the full ``diff_constraint`` scorer keyed off
    ``scoring_config.allowed_paths`` (which fails an empty change unless
    ``allow_empty`` is set, so a do-nothing agent that happens to pass the
    pre-existing tests cannot trivially pass this). This expresses the common
    "make the tests pass without touching anything outside these files".
    """
    test_verdict = score_test_command(inp)
    scope_verdict = score_diff_constraint(inp)
    checks = (
        CheckResult("tests_pass", test_verdict.passed is True, test_verdict.detail),
        CheckResult("within_scope", scope_verdict.passed is True, scope_verdict.detail),
    )
    return from_checks("custom", checks, all_label="custom check(s)")


#: Registry of named custom scorers. Extend it via :func:`register_custom_scorer`.
CUSTOM_SCORERS: dict[str, "object"] = {
    "tests_pass_and_diff_scope": _tests_pass_and_diff_scope,
}


def register_custom_scorer(name: str, scorer) -> None:
    """Register (or replace) a custom scorer under ``name``."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("custom scorer name must be a non-empty string")
    if not callable(scorer):
        raise TypeError("custom scorer must be callable")
    CUSTOM_SCORERS[name] = scorer


def available_custom_scorers() -> list[str]:
    """Names of the registered custom scorers, sorted."""
    return sorted(CUSTOM_SCORERS)


def score_custom(inp: ScoreInput) -> ScoreVerdict:
    """Dispatch to the custom scorer named by ``scoring_config.name``."""
    name = inp.config.get("name")
    scorer = CUSTOM_SCORERS.get(name) if isinstance(name, str) else None
    if scorer is None:
        return errored(
            "custom",
            f"unknown custom scorer {name!r} "
            f"(available: {', '.join(available_custom_scorers()) or 'none'})",
            name=name,
        )
    verdict = scorer(inp)
    # Normalise the reported method so every custom run reads as 'custom'.
    if verdict.method == "custom":
        return verdict
    return ScoreVerdict(
        "custom", verdict.outcome, verdict.passed, verdict.detail, verdict.checks, verdict.extra
    )
