# Commit note — Milestone 8

**Commit message:** `Add evaluation scoring and reports`

## What this commit adds

- `src/code_agent_runtime/scoring/` — the scoring layer:
  - `scorer.py` — `Outcome`, `ScoreInput`, `ScoreVerdict`, `CheckResult`,
    constructor helpers, `score_none`, and the `score_run` dispatcher (lazy
    per-method imports to stay below the runtime).
  - `test_scorer.py`, `expected_files.py`, `diff_scorer.py`, `custom.py` — the four
    scoring methods plus the custom-scorer registry/hook and one shipped composite.
  - `suite.py` — `EvalRecord`, `SuiteResult`, `build_agent`, `run_suite`,
    `write_suite_result` / `load_suite_result`.
- `src/code_agent_runtime/reports/` — `suite_to_markdown`, `suite_to_html`.
- `tasks/schema.py` — optional `scoring_config` with per-method validation.
- Runtime: `agent_loop._score` delegates to `scoring.score_run` (passes the diff +
  live workspace; scores before cleanup).
- `agents/solutions.py` — `SOLUTIONS` extended for the new scoring-variant tasks.
- Example tasks: `refactor/sum-range-diff-scope`, `bugfix/sum-range-expected-files`,
  `cli/add-shout-flag-custom`.
- CLI: `eval run` / `eval report`; `info` reports Milestone 8.
- `scripts/02_generate_report.py`; `/results/` gitignored.
- Tests: `tests/test_scoring.py`, `tests/test_eval.py`; `tests/test_scaffold_layout.py`
  extended.
- Docs/site: `docs/RESULTS.md` (real baseline table), `docs/ARCHITECTURE.md`,
  `docs/METHODOLOGY.md`, `README.md`; `evals.html`, `results.html`,
  `task-format.html`, `index.html`, `architecture.html`, `roadmap.html`,
  `limitations.html`; Milestone 8 milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (scoring/reports use only the stdlib + existing modules).
No paid API. Generated eval artifacts under `results/` are **gitignored**; the
committed result table in `docs/RESULTS.md` is the canonical, reproducible record.
The new example tasks reuse the existing committed fixtures (no new fixtures).

## Honesty notes

A passing test command is evidence, not proof, of correctness, and the task set
is tiny — results are illustrative, not statistically powerful. `diff_constraint`
scores *scope*, not correctness, and ignores Python bytecode caches as build
noise. Runtime is wall-clock and machine-dependent; only verdicts and tool/command
counts are deterministic. The `cli/add-shout-flag` test-command task passes under
the mock agent because the fixture's tests do not cover the new flag — surfaced in
the results notes as a coverage caveat, not hidden.

## Verification at commit time

- `python3 -m pytest -q` passes (git-dependent scope assertions skip if `git` is
  unavailable).
- `python3 scripts/02_generate_report.py` writes the `results/` artifacts and
  prints the Markdown report.
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks` prints the
  report; `eval report results/raw/eval.json` re-renders it.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
