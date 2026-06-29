# Milestone 9 — Regression comparison and flakiness analysis

## Summary

Two analyses over the `SuiteResult` JSON files that Milestone 8 produces, plus a
*rerun mode* that generates the input for the second:

- **Regression comparison** (`compare_suites`) diffs a *baseline* result against a
  *candidate* result, keyed by `(task_id, agent)`, and buckets every key as
  **improved**, **regressed**, **unchanged**, **flaky**, **added**, or **removed**.
  The headline signal is the pass/fail boolean: a key is *improved* only if it
  gained a pass and *regressed* only if it lost one. Any other outcome transition
  (e.g. `failed → error`) is *unchanged* in pass/fail terms with the change shown
  in `detail`, so nothing is silently dropped.
- **Flakiness analysis** (`analyze_flakiness`) aggregates several repeats of the
  *same* suite and flags any key whose scored outcome was not identical on every
  repeat. The deterministic mock/scripted/probe agents are flake-free by
  construction, so the baseline reports **zero** flaky keys — a determinism check
  the tests assert, not a claim the analyser assumes.
- **Rerun mode** (`run_repeated`) runs the task×agent matrix N times, reusing one
  config and registry so the only thing that can vary between repeats is genuine
  run-to-run non-determinism. `merge_suites` concatenates repeats into one
  multi-record `SuiteResult`, which lets `compare_suites` surface within-side
  flakiness too.

Both report types are pure data with JSON round-trips and Markdown renderers, and
two new CLI verbs (`eval compare`, `eval rerun`) drive them with CI-friendly exit
codes.

## Deliverables

- `src/code_agent_runtime/scoring/regression.py`:
  - `compare_suites` → `RegressionComparison` of `RegressionEntry` (category,
    baseline/candidate outcome+passed, detail, per-side flaky flags); category
    constants `IMPROVED/REGRESSED/UNCHANGED/FLAKY/ADDED/REMOVED`; `_collapse`
    (group repeats per key) and `_classify` (pass-gain/pass-loss logic).
  - `analyze_flakiness` → `FlakinessReport` of `FlakinessEntry` (runs, outcomes,
    pass/fail counts, `flaky`, `signal_varied`, `pass_rate`, `distinct_outcomes`).
  - JSON read/write: `write_comparison` / `load_comparison`, `write_flakiness` /
    `load_flakiness`; `REGRESSION_SCHEMA_VERSION`.
- `src/code_agent_runtime/scoring/suite.py`: `run_repeated` (rerun mode, injectable
  clock) and `merge_suites`.
- `src/code_agent_runtime/reports/regression.py`: `regression_to_markdown` (a
  per-category summary + one table per non-empty bucket) and
  `flakiness_to_markdown` (summary + per-key outcomes table); both reuse the suite
  report's cell sanitiser so a stray pipe/newline cannot break a row.
- `cli.py`: `eval compare BASELINE CANDIDATE` (exit 1 iff any regression) and
  `eval rerun [...] --repeats N` (exit 1 iff any flake); `info` now reports
  Milestone 9.
- `scripts/03_regression_demo.py`: reproducible demo — flakiness over the repeated
  suite (0 flaky) and a `mock → scripted` regression comparison (all improved /
  unchanged). Writes `results/` artifacts (gitignored).
- Tests: `tests/test_regression.py` (23 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 9 notes.
- Docs/site: `docs/RESULTS.md` (regression + flakiness section),
  `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`, `README.md`; website `evals.html`,
  `results.html`, `roadmap.html`, `index.html`.

## Category semantics (vs. the plan's checklist)

| Required bucket | Rule |
| --- | --- |
| improved | key existed on both sides, not flaky, and *gained* a pass (`pass_status` baseline ≠ pass, candidate = pass) |
| regressed | not flaky and *lost* a pass (baseline = pass, candidate ≠ pass) |
| unchanged | not flaky and neither gained nor lost a pass (outcome change, if any, noted in `detail`) |
| flaky | a side had repeated records that disagreed on outcome |
| added / removed | key present in only the candidate / only the baseline |

The plan lists improved / regressed / unchanged / flaky; `added` / `removed` are
the honest extra buckets for keys that exist on only one side (e.g. a task the
solver skips), so the four named buckets are never silently padded.

## Design notes / decisions

- **Pass/fail is the regression signal; outcome change is metadata.** Improved /
  regressed are defined solely by gaining or losing a pass. A `failed → error`
  transition is real and is recorded in `detail`, but it is not a "regression" in
  the sense that matters for a green-vs-red gate. This keeps the headline buckets
  crisp and documented rather than overloaded.
- **Flaky wins over improved/regressed.** If a key flipped within either side's
  repeats, its pass/fail delta cannot be trusted, so it is bucketed `flaky` and
  excluded from improved/regressed. Flakiness is therefore reachable from a single
  `compare` of merged rerun results, not only from `analyze_flakiness`.
- **Verdict flakiness ignores wall-clock; effort variance is a separate signal.** A
  key is flaky iff its *scored outcome* varied. Runtime is excluded (always noisy);
  tool/command-count variation with a stable verdict is reported as `signal_varied`
  but never counted as a flake — informative for a future model agent, not a defect
  for the deterministic ones.
- **Rerun reuses config and registry.** `run_repeated` builds the config and
  registry once and passes them to each `run_suite`, so a difference between
  repeats reflects the runtime, not setup churn.
- **No new dependency, no runtime import.** `regression.py` imports only the
  scoring layer; it stays below the runtime in the import graph like the rest of
  `scoring`. Reports import scoring, never the runtime.
- **CI-friendly exit codes.** `eval compare` exits 1 on any regression; `eval
  rerun` exits 1 on any flake. Pass/fail counts remain data in the report.

## Honest limitations (carried into docs)

- **Two single-run files cannot reveal flakiness.** With one record per key,
  `compare` can only see improved/regressed/unchanged; flakiness needs repeats
  (`eval rerun`, or feeding a merged rerun result into `compare`).
- **The deterministic baseline cannot regress against itself**, so the *regressed*
  and *flaky* buckets are demonstrated on synthetic "fake agent versions" in the
  tests; the script demo shows *improved* / *unchanged* on real data.
- **Flakiness here is outcome flakiness.** It does not yet model partial flakiness
  rates beyond pass-count, nor statistical confidence — small repeat counts make it
  a smoke check, not a flake-probability estimate.
- **Regression/flakiness reports are Markdown + JSON only** this milestone (no
  standalone HTML yet); the suite report still has both.

## Validation

- `python3 -m pytest -q` — full CPU-only suite passes (`tests/test_regression.py`
  added, 23 cases).
- `python3 scripts/03_regression_demo.py` — writes `results/raw/{flakiness,
  eval_mock,eval_scripted,regression_mock_vs_scripted}.json` and
  `results/reports/{flakiness,regression_mock_vs_scripted}.md`; prints both reports.
  Reports 0 flaky over 12 keys and 4 improved / 0 regressed for `mock → scripted`.
- `PYTHONPATH=src python3 -m code_agent_runtime eval rerun --dir tasks --repeats 3`
  — flakiness report (0 flaky); `--json` for the machine-readable form.
- `PYTHONPATH=src python3 -m code_agent_runtime eval compare a.json b.json` — diffs
  two saved suite results; exit 1 on a regression.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 10 — Optional cost-controlled LLM adapter.
