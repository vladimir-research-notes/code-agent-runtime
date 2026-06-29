# Milestone 8 — Scoring and evaluation reports

## Summary

Turn finished runs into **verdicts** and aggregate them into a **reportable
suite**. A new `scoring/` package implements all four scoring methods the task
schema named (`test_command`, `expected_files`, `diff_constraint`, `custom`) plus
a suite runner; a new `reports/` package renders a suite as Markdown or HTML. The
runtime loop now delegates scoring to this layer, passing the evidence it already
gathered (test result, captured diff, live workspace) — so the per-run `score`
shape is unchanged for existing tasks and the richer methods light up for the new
ones.

This closes the long-standing "minimal scoring" limitation: `expected_files`,
`diff_constraint`, and `custom` previously resolved to `not_scored` with a
"Milestone 8" note; they now produce real verdicts, each demonstrated end to end
by a shipped example task with a deterministic scripted solution.

## Deliverables

- `src/code_agent_runtime/scoring/`:
  - `scorer.py` — the vocabulary (`Outcome`, `ScoreInput`, `ScoreVerdict`,
    `CheckResult`), constructor helpers, the `score_none` scorer, and the
    `score_run` dispatcher (imports the per-method scorers lazily to keep
    `scoring` below the runtime in the import graph).
  - `test_scorer.py` — `score_test_command` (pass iff the test command exited 0;
    timeout → fail).
  - `expected_files.py` — `score_expected_files` (`present` / `absent` /
    `contains`; workspace-confined path resolution; missing workspace →
    `not_scored`).
  - `diff_scorer.py` — `score_diff_constraint` (`allowed_paths`,
    `forbidden_paths`, `max_files`, `allow_empty`); `changed_paths` /
    `matches_any` helpers; `DEFAULT_IGNORED_PATHS` drops bytecode caches from
    scope analysis.
  - `custom.py` — `CUSTOM_SCORERS` registry, `register_custom_scorer`,
    `available_custom_scorers`, `score_custom`, and the shipped composite
    `tests_pass_and_diff_scope` (tests pass **and** change in scope).
  - `suite.py` — `EvalRecord`, `SuiteResult`, `build_agent`, `run_suite`
    (wall-clock timed, injectable clock), `write_suite_result` /
    `load_suite_result`, `DEFAULT_AGENTS`, `SCHEMA_VERSION`.
- `src/code_agent_runtime/reports/`:
  - `markdown.py` — `suite_to_markdown` (the result table + honest notes).
  - `html.py` — `suite_to_html` (standalone, colour-coded HTML).
- Task schema: optional `scoring_config` field with method-specific validation
  (`tasks/schema.py`).
- Runtime: `agent_loop._score` delegates to `scoring.score_run`, passing the diff
  and the live workspace; scored before workspace cleanup.
- Agents: `SOLUTIONS` extended so the new scoring-variant tasks reuse the existing
  fixture solutions (one builder per fixture, not per id).
- Example tasks: `refactor/sum-range-diff-scope` (diff_constraint),
  `bugfix/sum-range-expected-files` (expected_files),
  `cli/add-shout-flag-custom` (custom).
- CLI: `eval run` (task×agent matrix → result file + Markdown/HTML report) and
  `eval report` (re-render a saved result file); `info` now reports Milestone 8.
- Script: `scripts/02_generate_report.py` (runs the default suite, writes
  `results/` artifacts). `/results/` is gitignored.
- Tests: `tests/test_scoring.py`, `tests/test_eval.py`; `tests/test_scaffold_layout.py`
  extended for the Milestone 8 notes.
- Docs/site: `docs/RESULTS.md` populated with the real baseline table;
  `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`, `README.md`; website pages
  `evals.html`, `results.html`, `task-format.html`, `index.html`,
  `architecture.html`, `roadmap.html`, `limitations.html`.

## Scoring methods (vs. the plan's checklist)

| Required | Where | Verdict logic |
| --- | --- | --- |
| test pass/fail | `test_scorer.py` | pass iff `run_tests` exited 0 |
| expected file checks | `expected_files.py` | `present`/`absent`/`contains` all hold |
| diff constraints | `diff_scorer.py` | every changed path in `allowed_paths`, none forbidden, within `max_files`, non-empty |
| custom scorer hook | `custom.py` | named scorer from the in-code registry |

Result summary fields (per the plan): the `EvalRecord` / report table carries
task id, agent, pass/fail, runtime (wall-clock), tool-call count, command count,
and a failure reason; plus scoring method, blocked-call count, and phase reached.

## Design notes / decisions

- **Scoring is a pure function of evidence.** A `ScoreInput` carries only data the
  run already produced (test result, diff, live workspace), so a verdict is
  reproducible and unit-testable without re-running anything.
- **Scored before cleanup.** The loop scores at the `SCORING` phase, before the
  `finally` that removes the workspace, so `expected_files` can read it.
- **No import cycle.** The runtime depends on `scoring`; `scoring` never imports
  the runtime at module load (the suite runner imports it lazily inside the
  function). A test asserts `Outcome` equals `RunOutcome` so the shared string
  vocabulary cannot drift.
- **`diff_constraint` is a constraint, not an achievement.** It checks scope, not
  correctness, and fails an empty change by default (so a do-nothing agent does
  not trivially "stay in scope"). The shipped `custom` composite pairs it with the
  test command to express "fix it, but only touch these files".
- **Bytecode noise is ignored in scope analysis.** `__pycache__` / `*.pyc` written
  by a test run are build artifacts, not authored changes; `changed_paths` drops
  them (mirroring the workspace copy-ignore and the repo `.gitignore`).
- **Custom scorers are code, not task imports.** A task selects a scorer by name
  and supplies params; it never names a Python import path. This keeps scoring
  deterministic and avoids importing task-specified code.
- **Wall-clock lives in the suite, not the run.** `RunResult` stays timing-free and
  deterministic; the suite times each `run_task` with an injectable clock.

## Honest limitations (carried into docs)

- A passing test command is **evidence, not proof**, of correctness; small task
  counts make results illustrative, not statistically powerful.
- `expected_files` checks existence/substrings, not semantic equivalence;
  `diff_constraint` matches by glob and treats `*` as spanning `/`.
- Runtime is wall-clock and machine-dependent; only the tool/command counts and
  verdicts are deterministic.
- `cli/add-shout-flag` (the `test_command` variant) **passes under the mock agent**
  because the fixture's existing tests do not exercise the new flag — an honest
  reminder that a test-command pass is bounded by test coverage. The `custom`
  variant distinguishes mock from scripted by also requiring an in-scope change.

## Validation

- `python3 -m pytest -q` — all tests pass (`tests/test_scoring.py`,
  `tests/test_eval.py` added). Git-dependent scope assertions skip if `git` is
  absent.
- `python3 scripts/02_generate_report.py` — runs the default suite and writes
  `results/raw/eval.json`, `results/reports/eval.md`, `results/reports/eval.html`.
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks` — prints the
  Markdown report; `--json`, `--out`, `--report`, and `eval report` work.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 9 — Regression comparison and flakiness analysis.
