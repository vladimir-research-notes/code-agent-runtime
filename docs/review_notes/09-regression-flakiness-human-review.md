Human review: Milestone 9 — Regression comparison and flakiness analysis

TL;DR
Adds two analyses over the Milestone 8 `SuiteResult` JSON files. `compare_suites`
diffs a baseline result against a candidate, keyed by `(task_id, agent)`, and
buckets every key as improved / regressed / unchanged / flaky / added / removed —
improved/regressed driven by the pass/fail boolean (gained vs. lost a pass), other
outcome transitions kept as unchanged with the change shown in `detail`.
`analyze_flakiness` aggregates N repeats of the same suite and flags any key whose
scored outcome was not identical on every repeat; the deterministic baseline shows
zero flaky keys. Rerun mode (`run_repeated`) runs the matrix N times reusing one
config/registry, and `merge_suites` lets a merged rerun result feed `compare`
(surfacing within-side flakiness). Both reports round-trip to JSON and render to
Markdown; two CLI verbs (`eval compare`, `eval rerun`) drive them with CI-friendly
exit codes. Covered by `tests/test_regression.py` (23 cases); the full suite passes.

What changed
- Added `src/code_agent_runtime/scoring/regression.py` (`compare_suites`,
  `analyze_flakiness`, dataclasses, JSON read/write).
- `scoring/suite.py`: `run_repeated`, `merge_suites`.
- `scoring/__init__.py`: exports the new API.
- Added `src/code_agent_runtime/reports/regression.py`
  (`regression_to_markdown`, `flakiness_to_markdown`); `reports/__init__.py` exports.
- `cli.py`: `eval compare` / `eval rerun`; milestone constants bumped to 9/10.
- `scripts/03_regression_demo.py` (writes gitignored `results/`).
- Tests: `tests/test_regression.py`; extended `tests/test_scaffold_layout.py`.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `README.md`, and the website (evals, results, roadmap, index).

What should be checked later
- Category semantics. Confirm the rules match intent: *improved* = gained a pass,
  *regressed* = lost a pass, *unchanged* = neither (outcome change, if any, recorded
  in `detail`), *flaky* = a side's repeats disagreed, *added* / *removed* = key on
  only one side. In particular, confirm that `failed → error` is intentionally
  *unchanged* (no pass lost) and `passed → error` is *regressed* (pass lost).
- Flaky wins over improved/regressed. A key that flipped within a side is bucketed
  flaky and excluded from improved/regressed. Confirm that precedence is what you
  want for merged rerun inputs.
- Flakiness definition. A key is flaky iff its scored *outcome* varied across
  repeats. Runtime is excluded (noisy); tool/command-count variation with a stable
  verdict is `signal_varied`, reported but not counted as a flake. Confirm that
  boundary (especially `signal_varied` not being a flake).
- The `added`/`removed` extras. The plan names four buckets; `added`/`removed`
  carry keys present on only one side (e.g. the security task the scripted solver
  skips). Confirm you want them as explicit buckets rather than dropped.
- Exit codes. `eval compare` exits 1 on any regression; `eval rerun` exits 1 on any
  flake. Confirm those gates match your CI intent (pass/fail counts stay data in
  the report, not the exit code).
- Re-keying in the demo script. `03_regression_demo.py` compares `mock` vs
  `scripted` by re-labelling the scripted records onto the `mock` agent name so the
  comparator matches by task. Confirm this illustrative re-keying is acceptable (it
  only affects the demo; the unit tests use straightforward same-key comparisons).
- Schema. `RegressionComparison`/`FlakinessReport` are `schema_version: 1`. Confirm
  the fields suffice for later milestones (e.g. a case study comparing real runs).

Technical risks
- Low. No new dependency; the analyses are pure functions over plain data and are
  unit-tested for every bucket (improved/regressed/unchanged/flaky/added/removed),
  flakiness detection, signal-vs-verdict variance, JSON round-trips, the Markdown
  reports, and the CLI exit codes. Determinism is asserted by re-running the real
  suite and checking 0 flaky and no signal variation. The main interpretive risk is
  reading "0 regressions" as "candidate is correct" — it means only "no key lost a
  pass relative to baseline"; the reports state this in their notes.

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_regression.py -q`
- `python3 scripts/03_regression_demo.py`
- `PYTHONPATH=src python3 -m code_agent_runtime eval rerun --dir tasks --repeats 3`
- `PYTHONPATH=src python3 -m code_agent_runtime eval rerun --dir tasks --agent mock --json`
- `PYTHONPATH=src python3 -m code_agent_runtime eval compare results/raw/eval_mock.json results/raw/eval_scripted.json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
