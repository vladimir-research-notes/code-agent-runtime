# Evaluation methodology

> **Status:** Milestone 10. Scoring, the suite runner, result reports, and
> regression/flakiness analysis are implemented; the deterministic baseline has
> been run — see [`RESULTS.md`](RESULTS.md). The optional cost-controlled LLM
> adapter adds a model-backed agent that is disabled and offline by default; no
> paid call is made in tests.

## Goal

Measure coding-agent behavior in a way that is **reproducible**, **inspectable**,
and **honest about uncertainty** — not to produce a leaderboard.

## Units of evaluation

- **Task** — a versioned unit of work with a fixture repo, prompt, allowed
  tools, and a deterministic success check (typically a test command).
- **Run** — one execution of one agent on one task, producing a trace.
- **Suite** — a collection of tasks run across one or more agents.

## What we measure

| Signal | Source | Notes |
| --- | --- | --- |
| Task success | `test_command` / `expected_files` scorer | Primary pass/fail. |
| Diff conformance | `diff_constraint` scorer (git diff vs. `allowed_paths`) | Did it stay in scope? |
| Combined checks | `custom` scorer (e.g. tests pass AND in scope) | Compose signals into one verdict. |
| Tool-call count | run record | Effort / efficiency proxy. |
| Command count | run record | Shell activity. |
| Runtime | wall-clock (suite layer) | Bounded by per-task timeout; machine-dependent. |
| Failure reason | scorer detail / error | Why a run failed, not just that it did. |

## Baselines

- **Mock agent** — deterministic, ignores task content; establishes a floor.
- **Scripted agent** — deterministic, follows a fixed recipe per task; tests the
  harness end-to-end without a model.
- **Offline LLM agent (fake client)** — the Milestone 10 `llm` agent driven by a
  deterministic fake client that replays a task's known-good solution through the
  model wire format. It exercises the model-backed path — and the budget guard,
  cache, and transcript redaction — with no API key and no spend. It demonstrates
  the *harness*, not genuine model reasoning, so it is a plumbing/cost baseline,
  not a capability measurement.
- **Optional real LLM / imported runs** — cost-guarded and clearly labeled.

## Cost control for model runs

A real model run is only admissible if its spend is bounded *before* the call.
The Milestone 10 adapter enforces that with four mechanisms, all exercised offline
by the fake client:

- **Hard pre-call budget guard.** Each call's worst case — estimated input tokens
  plus the full `max_tokens` of output, at the model's price — is priced *before*
  the client is contacted. If it could push cumulative spend past `--max-cost-usd`,
  the call is refused (`BudgetExceeded`). Actual usage is recorded after the call,
  so cumulative spend tracks reality and never exceeds the cleared worst case.
- **Unpriced ⇒ refused.** A model with no price in the table and no explicit
  override cannot be bounded, so the guard refuses it rather than guessing.
  Pricing is *approximate published list pricing* and must be verified before a
  paid run.
- **Response cache.** Identical requests are served from a content-hash cache for
  free, so re-runs neither re-spend nor introduce non-determinism.
- **Transcript redaction.** Credential-shaped text is scrubbed (reusing the
  sandbox secret scanner) from what is sent to and stored from the model.

A **dry-run** mode (`run --agent llm --dry-run`) prints the first request and its
estimated worst-case cost while making zero calls — the safe way to preview a paid
run. The real `ClaudeAPIClient` lazily imports `anthropic`, so neither importing
the package nor the default test suite requires the SDK or a key.

## Reproducibility rules

- Default tests are CPU-only and require no paid API.
- Randomness is controlled or recorded so runs can be repeated.
- Each reported number links to a trace artifact.

## Threats to validity

- Small task counts: results are illustrative, not statistically powerful.
- Fixture realism: tiny repos may not reflect real codebases.
- Scorer gaps: a passing test command does not guarantee a correct change.

## Scoring methods

- `test_command` — pass iff the test command exits 0 (a timeout is a failure).
- `expected_files` — pass iff named files exist / are absent / contain text.
- `diff_constraint` — pass iff the change stays within `allowed_paths` (and within
  `max_files`, touching no `forbidden_paths`, non-empty unless `allow_empty`). A
  *constraint*, not a correctness check.
- `custom` — a named scorer from an in-code registry; the shipped
  `tests_pass_and_diff_scope` combines a correctness check with a scope check.
- `none` — judged by inspection (e.g. the sandbox demo); reported `not_scored`.

Build artifacts (`__pycache__`, `*.pyc`) are ignored in diff-scope analysis.

## Comparing runs: regression and flakiness

Two result files (e.g. an agent before and after a change) are compared by
`compare_suites`, keyed by `(task_id, agent)`. The headline signal is the pass/fail
boolean:

- **improved** — the key gained a pass it did not have;
- **regressed** — the key lost a pass it had;
- **unchanged** — neither gained nor lost a pass (any other outcome change, e.g.
  `failed → error`, is recorded in the report's `detail`, not silently dropped);
- **flaky** — a side's repeated records disagreed on outcome;
- **added** / **removed** — the key exists in only one of the two files.

*Flakiness* is measured by re-running the same suite N times (`run_repeated`, the
*rerun mode*) and flagging any key whose scored outcome was not identical on every
repeat (`analyze_flakiness`). Verdict flakiness deliberately ignores wall-clock
runtime (always noisy); tool/command-count variation with a stable verdict is
reported as a *signal* difference, not a flake. The deterministic baseline agents
produce **zero** flaky keys — a determinism check, asserted by the tests.

A "0 regressions" comparison means *no key lost a pass relative to the baseline* —
not that the candidate is correct. Small repeat counts make flakiness a smoke
check, not a flake-probability estimate.

## Current implementation status

- [x] Scoring (`scoring/`), suite runner (`run_suite`), and Markdown/HTML reports
      (`reports/`) are implemented and exercised by the baseline in `RESULTS.md`.
- [x] Regression comparison and flakiness analysis (`scoring/regression.py`,
      `run_repeated`, `eval compare` / `eval rerun`) — Milestone 9.
- [x] Optional cost-controlled LLM adapter (`agents/llm/`, `run --agent llm`,
      `--dry-run`, `--allow-paid`) — Milestone 10. Offline by default; no paid
      call in tests.

## Relevant files

- `src/code_agent_runtime/scoring/` (incl. `regression.py`), `src/code_agent_runtime/reports/`
- `src/code_agent_runtime/agents/llm/` (client, pricing, budget, cache, protocol, agent, claude_client)
- `scripts/02_generate_report.py`, `scripts/03_regression_demo.py`, `scripts/05_llm_adapter_demo.py`
- `docs/RESEARCH_QUESTIONS.md`, `docs/RESULTS.md`, `docs/PLAN.md`
