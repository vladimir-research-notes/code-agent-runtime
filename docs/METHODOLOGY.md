# Evaluation methodology

> **Status:** Milestone 9. Scoring, the suite runner, result reports, and
> regression/flakiness analysis are implemented; the deterministic baseline has
> been run — see [`RESULTS.md`](RESULTS.md).

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
- **Optional LLM / imported runs** — cost-guarded and clearly labeled.

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

## Relevant files

- `src/code_agent_runtime/scoring/` (incl. `regression.py`), `src/code_agent_runtime/reports/`
- `scripts/02_generate_report.py`, `scripts/03_regression_demo.py`
- `docs/RESEARCH_QUESTIONS.md`, `docs/RESULTS.md`, `docs/PLAN.md`
