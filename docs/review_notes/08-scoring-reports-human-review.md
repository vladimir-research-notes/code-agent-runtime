Human review: Milestone 8 — Scoring and evaluation reports

TL;DR
Adds a `scoring/` layer that turns a finished run into a verdict and a `reports/`
layer that renders a suite as Markdown/HTML. All four scoring methods are
implemented — `test_command`, `expected_files`, `diff_constraint`, and `custom`
(an in-code scorer registry with one shipped composite) — plus an optional
`scoring_config` task field with per-method validation. The runtime loop delegates
scoring to `score_run`, passing the test result, the captured diff, and the live
workspace, and scores before workspace cleanup so filesystem checks work. A suite
runner (`run_suite`) produces a `SuiteResult` of per-run `EvalRecord`s (task id,
agent, pass/fail, runtime, tool/command counts, failure reason) that serialises to
JSON and reports to a table. New CLI `eval run` / `eval report`; new
`scripts/02_generate_report.py`; `/results/` gitignored. Three example tasks
(diff_constraint, expected_files, custom) reuse existing fixtures with scripted
solutions. Covered by `tests/test_scoring.py` and `tests/test_eval.py`; the full
suite passes.

What changed
- Added `src/code_agent_runtime/scoring/` (`scorer.py`, `test_scorer.py`,
  `expected_files.py`, `diff_scorer.py`, `custom.py`, `suite.py`, `__init__.py`).
- Added `src/code_agent_runtime/reports/` (`markdown.py`, `html.py`, `__init__.py`).
- `tasks/schema.py`: optional `scoring_config` + `_validate_scoring_config`.
- `runtime/agent_loop.py`: `_score` delegates to `scoring.score_run`.
- `agents/solutions.py`: `SOLUTIONS` mapped for the new task ids.
- Tasks: `refactor/sum-range-diff-scope`, `bugfix/sum-range-expected-files`,
  `cli/add-shout-flag-custom`.
- `cli.py`: `eval run` / `eval report`; milestone constants bumped.
- `scripts/02_generate_report.py`; `.gitignore` adds `/results/`.
- Tests: `tests/test_scoring.py`, `tests/test_eval.py`; extended
  `tests/test_scaffold_layout.py`.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `README.md`, and the website (evals, results, task-format, index, architecture,
  roadmap, limitations).

What should be checked later
- Scoring semantics. Confirm the verdict rules match intent: `test_command` =
  exit-0 (timeout → fail); `expected_files` passes iff all of present/absent/
  contains hold; `diff_constraint` requires every changed path in `allowed_paths`,
  no forbidden path, within `max_files`, and a non-empty change unless
  `allow_empty`; `custom` dispatches to a named in-code scorer.
- `diff_constraint` is a *constraint*, not an *achievement* scorer. It checks scope,
  not correctness. Confirm the empty-change-fails default and the composite
  `custom` scorer (`tests_pass_and_diff_scope`) are the intended way to combine
  correctness with scope.
- Bytecode noise. `changed_paths` drops `__pycache__`/`*.pyc`/`*.pyo`/`*.pyd`/
  `.pytest_cache` from scope analysis. Confirm this default ignore set is right and
  that ignoring build artifacts (not authored changes) is acceptable; pass
  `ignore=()` to include everything.
- Coverage caveat in the results. `cli/add-shout-flag` (test_command) **passes
  under the mock agent** because the fixture tests do not exercise `--shout`. This
  is surfaced in `docs/RESULTS.md` and the report notes as a real reminder that a
  test pass is bounded by coverage — confirm you want it shipped that way (the
  `custom` variant is the discriminating version).
- `scoring_config` validation strictness. `expected_files` and `diff_constraint`
  reject unknown keys; `custom` requires `name` and allows arbitrary extra params
  for the named scorer. Confirm that's the right strictness boundary.
- Import layering. The runtime depends on `scoring`; `scoring` never imports the
  runtime at module load (the suite runner imports it lazily). A test asserts
  `scoring.Outcome == runtime.RunOutcome`. Confirm this is the layering you want.
- CLI exit codes. `eval run` returns 0 on a completed suite and 2 only if a run
  errored at the harness level — pass/fail is data in the report, not the exit
  code. Confirm that matches how you'd gate CI.
- Result-file schema. `SuiteResult.to_dict` is `schema_version: 1`; Milestone 9
  (regression comparison) will consume it. Confirm the fields are sufficient.

Technical risks
- Low. No new dependency; scorers are pure functions over plain data and are unit-
  tested per method (pass and fail paths, edge cases). The main risk is
  over-trusting a verdict: a green `test_command`/`custom` row means "the declared
  checks held", not "the change is correct". The reports state this in their notes,
  and `docs/RESULTS.md`/`docs/METHODOLOGY.md` repeat the caveats. Secondary: the
  glob matcher treats `*` as spanning `/` (fnmatch); confirm that suits your scope
  patterns (covered by tests).

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_scoring.py tests/test_eval.py -q`
- `python3 scripts/02_generate_report.py`
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks`
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --agent scripted --json`
- `PYTHONPATH=src python3 -m code_agent_runtime eval report results/raw/eval.json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
