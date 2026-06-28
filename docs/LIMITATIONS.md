# Limitations and non-goals

> **Status:** current as of Milestone 0. Updated at every milestone.

## What is true today

- The repository contains a Python package scaffold, a minimal CLI, a
  documentation skeleton, a multi-page static website, packaging metadata, and
  a CPU-only smoke test.
- Nothing about the agent runtime, tools, sandbox, tracing, or scoring is
  implemented yet.

## Known limitations

- **No sandbox.** There is no enforced isolation; see
  [`SECURITY_MODEL.md`](SECURITY_MODEL.md).
- **No evaluations.** [`RESULTS.md`](RESULTS.md) is intentionally empty.
- **No model integration.** There are no LLM calls and no Claude adapters yet.
- **Environment assumption.** Tests assume `python3` (3.10+) with `pytest`
  available. The repo uses a `src/` layout with a `conftest.py` path shim so the
  suite runs without an install; an editable install also works.

## Non-goals (from the project plan)

This repository is **not**:

- a production-secure sandbox;
- a replacement for any commercial coding agent;
- a claim that a custom agent beats commercial agents;
- a benchmark leaderboard;
- a large-scale paid-API evaluation;
- a web product or a tutorial.

## How limitations are tracked

Every milestone updates this file and the per-page "Open questions / limitations"
sections of the website. Claims are backed by tests, reproducible examples,
trace artifacts, result tables, or an explicit statement of a limitation.

## Relevant files

- `docs/PLAN.md`, `docs/SECURITY_MODEL.md`, `docs/RESULTS.md`
