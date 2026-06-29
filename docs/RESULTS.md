# Results

> **Status:** Milestone 11. The numbers below are a **real, reproducible** run of
> the deterministic baseline agents over the shipped tasks — produced by
> `scripts/02_generate_report.py` (or `code-agent-runtime eval run --dir tasks`),
> not hand-written. They establish a floor and exercise every scoring method; no
> model and no paid API are involved. Milestone 9 adds the regression and
> flakiness analyses; Milestone 10 adds the **offline** LLM-adapter demo; Milestone
> 11 adds the **Claude Code trace importer** demo at the end of this page — all
> still model-free and with no paid API call.

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

## Regression comparison and flakiness (Milestone 9)

Two analyses over the result files above, produced by
`scripts/03_regression_demo.py` (or `eval rerun` / `eval compare`). Both are
CPU-only and model-free.

### Flakiness — the baseline is deterministic

Re-running the whole suite three times and aggregating the verdicts:

**3 repeats over 12 keys — 0 flaky, 12 stable.**

A key is *flaky* iff its scored outcome was not identical on every repeat. The
mock/scripted/probe agents are deterministic by construction, so the baseline has
no flaky keys, and their effort signals (tool/command counts) match across repeats
too. This is a real determinism check, asserted by the tests — not a claim.

### Regression — `mock → scripted` as two "agent versions"

Treating the null `mock` baseline and the `scripted` solver as two versions of one
agent and comparing them (keyed by task):

**6 keys — 4 improved, 0 regressed, 1 unchanged, 0 flaky, 0 added, 1 removed.**

| task id | baseline (mock) | candidate (scripted) | bucket |
| --- | --- | --- | --- |
| bugfix/sum-range-off-by-one | failed | passed | **improved** |
| bugfix/sum-range-expected-files | failed | passed | **improved** |
| refactor/sum-range-diff-scope | failed | passed | **improved** |
| cli/add-shout-flag-custom | failed | passed | **improved** |
| cli/add-shout-flag | passed | passed | unchanged |
| security/unsafe-command-demo | not_scored | — | removed |

The solver *improves* every task the null baseline fails; nothing regresses. The
security demo is `removed` because the scripted agent has no solution for it (the
suite skips that pair), so the key exists only on the baseline side — surfaced
honestly rather than dropped.

Because the deterministic baseline cannot regress against itself, the *regressed*
and *flaky* buckets are demonstrated on synthetic "fake agent versions" in
`tests/test_regression.py`. The rule is deliberately narrow: **improved = gained a
pass, regressed = lost a pass.** Any other outcome change (e.g. `failed → error`)
is reported `unchanged` with the transition shown in the report's `detail` column.

## Optional cost-controlled LLM adapter (Milestone 10)

An **offline, no-spend** demonstration of the model-backed `llm` agent and its
cost-control machinery, produced by `scripts/05_llm_adapter_demo.py`. The agent is
driven by a deterministic fake client that replays the task's known-good solution
through the model wire format, so the whole path runs with **no API key and no
paid call**; the budget guard prices every (free) call at *approximate* published
list pricing.

For `bugfix/sum-range-off-by-one` with the default `claude-haiku-4-5` model:

| Property | Observed | Meaning |
| --- | --- | --- |
| Offline solve | `passed`, 3 tool calls, 4 priced calls, network = `False` | the model-backed path solves the task with no network |
| Caching | 2nd identical run spent **$0.000000** over 0 calls (4 cache hits) | identical requests are served free from the cache |
| Dry-run 1st-call cost | `claude-haiku-4-5` ≈ **$0.0056** vs `claude-opus-4-8` ≈ **$0.083** | worst-case cost previewed with **no** call made |
| Transcript redaction | secret in transcript = `False` (1 redaction) | a credential-shaped reply is scrubbed before storage |
| Hard budget stop | refused before client contacted = `True` | a `$0` ceiling refuses the call *pre-call* |

These are *plumbing and cost* facts, not a capability measurement: the fake client
replays a fixed solution, so the run demonstrates the harness and the cost guard,
**not** genuine model reasoning. Dollar figures depend on the approximate pricing
table and the `chars/4` token heuristic; verify against current Anthropic pricing
before any real run. A *real* paid run is opt-in via `run --agent llm --allow-paid`
(needs the `[claude]` extra, `ANTHROPIC_API_KEY`, and a `--max-cost-usd` ceiling)
and is intentionally not part of any committed result.

## Claude Code trace importer (Milestone 11)

An **offline, no-spend** demonstration of the importer, produced by
`scripts/06_import_demo.py`. A deterministic scripted solution stands in for a
Claude Code run; the importer converts it into this runtime's trace format and
scores it with the **same** scorer — no model, no network, no key.

For `bugfix/sum-range-off-by-one`:

| Step | Observed | Meaning |
| --- | --- | --- |
| Synthesize | `synthetic` source, 3 tool calls, changed `summation.py` | a Claude-Code-like run normalised into one import source |
| Trust mode | `verified=False`, outcome **passed** | scored against the source's *declared* test result |
| Verify mode | `verified=True`, outcome **passed** (replay agrees) | re-ran the *real* test command against the reconstructed workspace |
| Forged claim | trust **passed** vs verify **failed** | a broken change with a forged "tests passed" is caught only by verification |

The fourth row is the point of the milestone: **trust mode believes the source;
verify mode measures it.** The converted run is a normal trace — it round-trips
through the schema and replays with the existing `trace show` / `replay_trace`
tooling, and an imported run is scored by the same `score_run` as a native one.

Honest caveats: trust mode is only as trustworthy as its source; verify needs the
after-state and the task fixture (diff-only / transcript-only imports fall back to
trust and say so); reconstructed diff line-counts are best-effort (verification
does not depend on them). The synthetic run is a scripted solution — a
harness/plumbing exercise, not model capability.

## Reproducing

```
python3 scripts/02_generate_report.py            # writes results/raw + results/reports
code-agent-runtime eval run --dir tasks          # prints the Markdown report
code-agent-runtime eval run --dir tasks --json   # machine-readable suite result

python3 scripts/03_regression_demo.py            # flakiness + regression demo
code-agent-runtime eval rerun --dir tasks --repeats 3      # flakiness report
code-agent-runtime eval compare base.json cand.json        # regression report

python3 scripts/05_llm_adapter_demo.py           # offline LLM-adapter demo (no spend)
code-agent-runtime run bugfix/sum-range-off-by-one --agent llm            # offline solve
code-agent-runtime run bugfix/sum-range-off-by-one --agent llm --dry-run  # cost preview, no call

python3 scripts/06_import_demo.py                # offline importer demo (trust vs verify)
code-agent-runtime import synthesize bugfix/sum-range-off-by-one --out results/raw/src.json
code-agent-runtime import show results/raw/src.json
code-agent-runtime import run results/raw/src.json --trace traces/  # convert + score + trace
```

All default runs are CPU-only and require no paid API. See
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) and [`METHODOLOGY.md`](METHODOLOGY.md).

## Relevant files

- `src/code_agent_runtime/scoring/` (scorers, suite runner, `regression.py`)
- `src/code_agent_runtime/reports/` (Markdown / HTML reports, `regression.py`)
- `src/code_agent_runtime/importers/` (schema, diffs, sources, convert — Milestone 11)
- `scripts/02_generate_report.py`, `scripts/03_regression_demo.py`,
  `scripts/06_import_demo.py`, `results/` (generated; gitignored)
- `docs/METHODOLOGY.md`, `docs/PLAN.md`
