# Limitations and non-goals

> **Status:** current as of Milestone 9. Updated at every milestone.

## What is true today

- The repository contains a Python package and CLI, a documentation skeleton, a
  multi-page static website, packaging metadata, and CPU-only tests.
- An **environment check** and a **repository hygiene scanner** exist
  (Milestone 1).
- A **versioned task format** (schema, loader, example tasks, `tasks` CLI;
  Milestone 2), a **tool registry** with seven structured core tools (`tools`
  CLI; Milestone 3), a **runtime loop** that drives mock/scripted agents over a
  task (`run` CLI; Milestone 4), **structured run tracing** (a JSON `Trace`
  schema, an opt-in recorder, and `run --trace`; Milestone 5), **trace
  replay/debugging tooling** (`trace show` / `trace report`; Milestone 6), and
  **permission policies and sandbox controls** (a `SandboxPolicy` enforced on
  every agent tool call, with output redaction; Milestone 7), **scoring and
  evaluation reports** (all four scoring methods, a suite runner, Markdown/HTML
  reports, and an `eval` CLI; Milestone 8), and **regression comparison with
  flakiness analysis** (diff two result files into improved/regressed/unchanged/
  flaky buckets, plus a rerun mode; `eval compare` / `eval rerun`; Milestone 9)
  are implemented.
- Optional cost-controlled model adapters are **not** implemented yet.
- **Regression judges only pass/fail.** A key is *improved* only if it gained a
  pass and *regressed* only if it lost one; a "0 regressions" comparison is not a
  correctness proof. Flakiness needs repeats (two single-run files cannot reveal
  it) and small repeat counts make it a smoke check, not a flake-probability
  estimate; the deterministic baseline shows zero flaky keys. Regression/flakiness
  reports are Markdown + JSON only (no standalone HTML yet).

## Known limitations

- **The sandbox is not a jail.** A `SandboxPolicy` is enforced on every agent tool
  call by default (allowed/denied paths, command allow/denylist, network flag,
  runtime/output caps) — see [`SECURITY_MODEL.md`](SECURITY_MODEL.md) — but it
  reduces blast radius, it does not contain malicious native code. Command matching
  is by program *name* (a renamed binary or absolute path to a copy is not caught);
  network enforcement is a heuristic denylist (a direct socket open is not blocked);
  there is **no** process/namespace isolation (a containerized runner is a future,
  optional capability); and `cpu_seconds` is enforced as a wall-clock bound. The
  hygiene scanner remains a separate commit-time guard.
- **Trace redaction is heuristic.** With the sandbox enabled (the default), command
  stdout/stderr, file contents, and diffs are scrubbed of credential-shaped strings
  before they enter a trace, using the same high-precision patterns as the hygiene
  scanner — so redaction can miss novel or obfuscated secrets and does not detect
  non-secret sensitive data. With `--no-sandbox` no redaction occurs. The default
  `--trace` destination (`traces/`) is gitignored to avoid accidental commits.
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
- `src/code_agent_runtime/sandbox/` (policy, permissions, secret_scanner)
- `src/code_agent_runtime/hygiene.py`, `src/code_agent_runtime/environment.py`
