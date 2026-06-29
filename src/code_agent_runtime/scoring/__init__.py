"""Scoring and evaluation (Milestone 8).

Turns finished runs into verdicts and aggregates them into a reportable suite.

Public API:

- :func:`score_run` — score one finished run per its task's ``scoring_method``;
  :class:`ScoreInput`, :class:`ScoreVerdict`, :class:`CheckResult`,
  :class:`Outcome` — the scoring vocabulary.
- The per-method scorers: :func:`score_test_command`, :func:`score_expected_files`,
  :func:`score_diff_constraint`, :func:`score_custom`, :func:`score_none`.
- The custom-scorer hook: :data:`CUSTOM_SCORERS`, :func:`register_custom_scorer`,
  :func:`available_custom_scorers`.
- The suite runner and result schema: :func:`run_suite`, :func:`run_repeated`,
  :func:`merge_suites`, :func:`build_agent`, :class:`EvalRecord`,
  :class:`SuiteResult`, :func:`write_suite_result`, :func:`load_suite_result`,
  :data:`DEFAULT_AGENTS`, :data:`SCHEMA_VERSION`.
- Regression comparison and flakiness analysis (Milestone 9):
  :func:`compare_suites` → :class:`RegressionComparison` of
  :class:`RegressionEntry`; :func:`analyze_flakiness` → :class:`FlakinessReport`
  of :class:`FlakinessEntry`; plus their JSON read/write helpers.

Scoring is a pure function of the evidence a run produced (test result, captured
diff, live workspace), so verdicts are reproducible and unit-testable. The
package deliberately does not import the runtime at module load; the suite runner
imports it lazily so the runtime can depend on scoring without a cycle.
"""

from __future__ import annotations

from .custom import (
    CUSTOM_SCORERS,
    available_custom_scorers,
    register_custom_scorer,
    score_custom,
)
from .diff_scorer import changed_paths, matches_any, score_diff_constraint
from .expected_files import score_expected_files
from .regression import (
    ADDED,
    CATEGORIES,
    IMPROVED,
    REGRESSED,
    REGRESSION_SCHEMA_VERSION,
    REMOVED,
    UNCHANGED,
    FLAKY,
    FlakinessEntry,
    FlakinessReport,
    RegressionComparison,
    RegressionEntry,
    analyze_flakiness,
    compare_suites,
    load_comparison,
    load_flakiness,
    write_comparison,
    write_flakiness,
)
from .scorer import (
    CheckResult,
    Outcome,
    ScoreInput,
    ScoreVerdict,
    Scorer,
    score_none,
    score_run,
)
from .suite import (
    DEFAULT_AGENTS,
    SCHEMA_VERSION,
    EvalRecord,
    SuiteResult,
    build_agent,
    load_suite_result,
    merge_suites,
    run_repeated,
    run_suite,
    write_suite_result,
)
from .test_scorer import score_test_command

__all__ = [
    # core
    "score_run",
    "ScoreInput",
    "ScoreVerdict",
    "CheckResult",
    "Outcome",
    "Scorer",
    # per-method scorers
    "score_test_command",
    "score_expected_files",
    "score_diff_constraint",
    "score_custom",
    "score_none",
    "changed_paths",
    "matches_any",
    # custom hook
    "CUSTOM_SCORERS",
    "register_custom_scorer",
    "available_custom_scorers",
    # suite
    "run_suite",
    "run_repeated",
    "merge_suites",
    "build_agent",
    "EvalRecord",
    "SuiteResult",
    "write_suite_result",
    "load_suite_result",
    "DEFAULT_AGENTS",
    "SCHEMA_VERSION",
    # regression + flakiness (Milestone 9)
    "compare_suites",
    "RegressionComparison",
    "RegressionEntry",
    "analyze_flakiness",
    "FlakinessReport",
    "FlakinessEntry",
    "write_comparison",
    "load_comparison",
    "write_flakiness",
    "load_flakiness",
    "REGRESSION_SCHEMA_VERSION",
    "CATEGORIES",
    "IMPROVED",
    "REGRESSED",
    "UNCHANGED",
    "FLAKY",
    "ADDED",
    "REMOVED",
]
