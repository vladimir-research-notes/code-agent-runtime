# Results

> **Status:** Milestone 8. The numbers below are a **real, reproducible** run of
> the deterministic baseline agents over the shipped tasks — produced by
> `scripts/02_generate_report.py` (or `code-agent-runtime eval run --dir tasks`),
> not hand-written. They establish a floor and exercise every scoring method; no
> model and no paid API are involved.

## Baseline suite

Six tasks across the deterministic agents (`mock`, `scripted`, and `probe` for the
security demo). The columns are the deterministic signals; **runtime is omitted
here because it is wall-clock and machine-dependent** — it appears in the generated
report (`results/reports/eval.{md,html}`), regenerated per machine.

| task id | agent | scoring method | result | tool calls | commands | failure reason |
| --- | --- | --- | --- | --- | --- | --- |
| bugfix/sum-range-off-by-one | mock | test_command | fail | 0 | 0 | test command failed (exit 1) |
| bugfix/sum-range-off-by-one | scripted | test_command | **pass** | 3 | 0 | |
| bugfix/sum-range-expected-files | mock | expected_files | fail | 0 | 0 | summation.py does not contain the fixed loop |
| bugfix/sum-range-expected-files | scripted | expected_files | **pass** | 3 | 0 | |
| refactor/sum-range-diff-scope | mock | diff_constraint | fail | 0 | 0 | no files were changed |
| refactor/sum-range-diff-scope | scripted | diff_constraint | **pass** | 3 | 0 | |
| cli/add-shout-flag | mock | test_command | pass | 0 | 0 | (see coverage caveat) |
| cli/add-shout-flag | scripted | test_command | **pass** | 2 | 0 | |
| cli/add-shout-flag-custom | mock | custom | fail | 0 | 0 | no files were changed |
| cli/add-shout-flag-custom | scripted | custom | **pass** | 2 | 0 | |
| security/unsafe-command-demo | mock | none | not_scored | 0 | 0 | |
| security/unsafe-command-demo | probe | none | not_scored | 8 | 0 | 7 calls blocked by policy |

**Totals:** 12 runs — 6 passed, 4 failed, 2 not scored, 0 errored.

Skipped (agent not applicable to task): `scripted` on the security demo (no
solution); `probe` on the five non-security tasks (no probe defined).

## How to read this

- **`result`** is the scored verdict. `not_scored` is for tasks judged by
  inspection (`scoring_method: none`), like the sandbox demo.
- **The scripted agent passes every solvable task**; the mock agent (the null
  baseline) fails the ones that require a change — confirming the harness and each
  scoring method discriminate a real change from no change.
- **`tool calls` / `commands` are deterministic** and reproducible across machines;
  the verdicts are too. Only runtime varies.

## Honest caveats

- **A passing test command is evidence, not proof.** `cli/add-shout-flag` (the
  `test_command` variant) **passes under the mock agent** even though the mock
  changes nothing — because the fixture's existing tests do not exercise the new
  `--shout` flag. This is a real reminder that a test-command pass is bounded by
  test coverage. The `cli/add-shout-flag-custom` variant is the discriminating
  version: its `custom` scorer requires the tests to pass **and** an in-scope
  change, so the do-nothing mock fails it.
- **`diff_constraint` scores scope, not correctness.** It asks "did the change stay
  within these files?", and fails an empty change by default. Combine it with a
  correctness check (as the `custom` composite does) for "fix it, but only here".
- **Small task counts make this illustrative, not statistically powerful.** This is
  a baseline floor and a harness exercise, not a benchmark.

## Reproducing

```
python3 scripts/02_generate_report.py            # writes results/raw + results/reports
code-agent-runtime eval run --dir tasks          # prints the Markdown report
code-agent-runtime eval run --dir tasks --json   # machine-readable suite result
```

All default runs are CPU-only and require no paid API. See
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) and [`METHODOLOGY.md`](METHODOLOGY.md).

## Relevant files

- `src/code_agent_runtime/scoring/` (scorers + suite runner)
- `src/code_agent_runtime/reports/` (Markdown / HTML reports)
- `scripts/02_generate_report.py`, `results/` (generated; gitignored)
- `docs/METHODOLOGY.md`, `docs/PLAN.md`
