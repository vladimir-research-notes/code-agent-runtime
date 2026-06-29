# Commit note — Milestone 9

**Commit message:** `Add regression comparison and flakiness analysis`

## What this commit adds

- `src/code_agent_runtime/scoring/regression.py` — the Milestone 9 analyses:
  - `compare_suites` → `RegressionComparison` / `RegressionEntry`, with the
    `improved/regressed/unchanged/flaky/added/removed` category vocabulary,
    `_collapse` (group repeated records per key) and `_classify` (pass-gain /
    pass-loss logic, flaky-wins).
  - `analyze_flakiness` → `FlakinessReport` / `FlakinessEntry` (outcomes, pass/fail
    counts, `flaky`, `signal_varied`, `pass_rate`).
  - JSON helpers `write_comparison` / `load_comparison`, `write_flakiness` /
    `load_flakiness`; `REGRESSION_SCHEMA_VERSION`.
- `src/code_agent_runtime/scoring/suite.py` — `run_repeated` (rerun mode) and
  `merge_suites`.
- `src/code_agent_runtime/scoring/__init__.py` — exports the above.
- `src/code_agent_runtime/reports/regression.py` — `regression_to_markdown`,
  `flakiness_to_markdown`; exported from `reports/__init__.py`.
- `cli.py` — `eval compare` / `eval rerun`; milestone constants bumped to 9/10.
- `scripts/03_regression_demo.py` — reproducible regression + flakiness demo
  (writes `results/`, gitignored).
- Tests: `tests/test_regression.py` (23 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 9 notes.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `README.md`; `evals.html`, `results.html`, `roadmap.html`, `index.html`;
  Milestone 9 milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (regression/reports use only the stdlib + existing scoring
modules). No paid API. Generated `results/` artifacts remain **gitignored**; the
committed result narrative in `docs/RESULTS.md` is the canonical record. No new
fixtures or example tasks (the comparison/flakiness tooling operates on the
existing suite output).

## Honesty notes

Regression is judged on the pass/fail signal: *improved* = gained a pass,
*regressed* = lost a pass; other outcome transitions are *unchanged* with the
change shown in `detail`. Flakiness is outcome flakiness over repeats; the
deterministic baseline never flakes, so the real demo shows 0 flaky and the
*regressed* / *flaky* buckets are exercised by synthetic fake-agent-version tests
rather than fabricated "real" data. Small repeat counts make flakiness a smoke
check, not a flake-probability estimate. Regression/flakiness reports are Markdown
+ JSON only this milestone (no standalone HTML yet).

## Verification at commit time

- `python3 -m pytest -q` passes (`tests/test_regression.py` added).
- `python3 scripts/03_regression_demo.py` writes the `results/` artifacts and
  prints the flakiness (0 flaky / 12 keys) and regression (4 improved / 0
  regressed for `mock → scripted`) reports.
- `PYTHONPATH=src python3 -m code_agent_runtime eval rerun --dir tasks --repeats 3`
  and `... eval compare a.json b.json` work; exit codes gate on flakes/regressions.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
