# Evaluation methodology

> **Status:** skeleton (Milestone 0). Describes the intended methodology. No
> evaluations have been run yet; see [`RESULTS.md`](RESULTS.md).

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
| Task success | test command exit / file checks | Primary pass/fail. |
| Diff conformance | git diff vs. constraints | Did it stay in scope? |
| Tool-call count | trace | Effort / efficiency proxy. |
| Command count | trace | Shell activity. |
| Runtime | wall-clock | Bounded by per-task timeout. |
| Failure reason | trace + scorer | Why a run failed, not just that it did. |

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

## Current implementation status

- [ ] Scoring, suite runner, and result reports are not implemented yet.

## Relevant files

- `docs/RESEARCH_QUESTIONS.md`, `docs/RESULTS.md`, `docs/PLAN.md`
