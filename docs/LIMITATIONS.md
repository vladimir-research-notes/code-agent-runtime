# Limitations and non-goals

> **Status:** current as of Milestone 5. Updated at every milestone.

## What is true today

- The repository contains a Python package and CLI, a documentation skeleton, a
  multi-page static website, packaging metadata, and CPU-only tests.
- An **environment check** and a **repository hygiene scanner** exist
  (Milestone 1).
- A **versioned task format** (schema, loader, example tasks, `tasks` CLI;
  Milestone 2), a **tool registry** with seven structured core tools (`tools`
  CLI; Milestone 3), a **runtime loop** that drives mock/scripted agents over a
  task (`run` CLI; Milestone 4), and **structured run tracing** (a JSON `Trace`
  schema, an opt-in recorder, and `run --trace`; Milestone 5) are implemented.
- Sandbox enforcement, replay tooling, full scoring, reports, and model adapters
  are **not** implemented yet.

## Known limitations

- **No sandbox.** There is no enforced runtime isolation; see
  [`SECURITY_MODEL.md`](SECURITY_MODEL.md). The hygiene scanner is a
  commit-time guard, not a runtime control. The runtime provides only workspace
  confinement and `allowed_tools` capability gating — no process isolation,
  resource limits, or network policy yet (Milestone 7).
- **Traces are not redacted.** A recorded trace stores command stdout/stderr as
  captured, so it may contain whatever a command printed (including secrets).
  Persisting traces of untrusted commands to a shared location is unsafe until
  the secret scanner lands (Milestone 7). The default `--trace` destination
  (`traces/`) is gitignored to avoid accidental commits.
- **Production trace timestamps are non-deterministic.** The recorder reads the
  real wall/monotonic clock by default (intended); tests inject a fake clock for
  reproducibility.
- **Hygiene secret detection is heuristic.** It uses high-precision patterns
  that favor avoiding false positives over catching every secret, so it can miss
  novel or obfuscated credentials. It is not a guarantee that no secret can be
  committed, and it does not detect non-secret sensitive data.
- **Hygiene scope is tracked files.** By default only `git ls-files` content is
  scanned; gitignored-but-present files are ignored on purpose, and bare
  `env`/`ENV` directories are not treated as virtualenvs (to avoid false
  positives). Use `--include-untracked` to widen scope.
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
- `src/code_agent_runtime/hygiene.py`, `src/code_agent_runtime/environment.py`
