# Limitations and non-goals

> **Status:** current as of Milestone 14 (final hardening completes the plan). Updated at every milestone.

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
  flaky buckets, plus a rerun mode; `eval compare` / `eval rerun`; Milestone 9),
  and an **optional cost-controlled LLM adapter** (a model-backed `llm` agent
  behind a hard pre-call budget guard, a response cache, transcript redaction, and
  a `--dry-run` cost preview; offline-by-default via a deterministic fake client,
  opt-in to a real Claude API run with `--allow-paid`; Milestone 10), and a
  **Claude Code trace importer** (normalise an external run into a `Trace` and
  score it with the same scorer, in verify or trust mode; `import` CLI;
  Milestone 11), a **reproducible case study** (13 tasks across all five
  categories, run by both baselines plus the sandbox probes into a committed result
  CSV, reports, and one trace per run; `scripts/07_case_study.py`; Milestone 12), a
  **polished, internally consistent multi-page website** (uniform six-section pages
  and self-contained inline-SVG diagrams, enforced by a website-quality test;
  Milestone 13), and **final hardening** (a `release-check` gate aggregating the
  release-readiness checks — source compiles, hygiene/no-secrets/no-large-artifacts,
  docs and website consistency, README quality, reproducibility, plus optional
  lint/tests; `release-check` / `scripts/08_final_checks.py`; Milestone 14) are
  implemented.
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
- **The LLM cost guard is bounded by its inputs.** Pricing is *approximate
  published list pricing* baked into a table (`agents/llm/pricing.py`) that **must
  be verified against current Anthropic pricing before a paid run**; it is
  overridable, and an unpriced model is refused rather than estimated. Token
  counts use a `chars/4` heuristic, not a real tokenizer — fine for the *worst
  case* the pre-call guard bounds (estimated input + full `max_tokens` of output),
  but not an exact predictor; actual usage is recorded from the provider after the
  call. The guard stops spend, it does not make a model correct.
- **The offline LLM agent is a harness exercise, not model reasoning.** Its
  default `FakeLLMClient` replays a task's *known-good solution* through the model
  wire format, so an offline `run --agent llm` "passing" reflects the scripted
  solution and the plumbing, not a model's capability. A real run is opt-in
  (`--allow-paid`, the `[claude]` extra, an API key, a `--max-cost-usd` ceiling)
  and is intentionally absent from tests and committed results.
- **Transcript redaction is heuristic.** It reuses the same high-precision
  credential patterns as the sandbox/hygiene scanner, so it can miss novel or
  obfuscated secrets and does not detect non-secret sensitive data; with
  `--no-redact-transcript` it is off.
- **An imported run is only as trustworthy as its mode.** The importer's *trust*
  mode scores the source's **declared** diff/test result — it believes the source.
  Only *verify* mode re-derives the verdict, by reconstructing the workspace from
  the imported after-state over the task fixture and re-running the task's real
  test command; a test proves a broken change with a forged "tests passed" is
  caught only in verify mode. Verify therefore needs the after-state *and* the
  task's fixture (the same baseline the external run started from for the
  reconstructed diff to be meaningful); diff-only and transcript-only imports
  carry no file content, so `auto` falls back to trust and says so.
- **Reconstructed diff counts are best-effort.** The importer rebuilds a
  `git_diff`-shaped summary from a unified diff text (or two content snapshots)
  without invoking `git`; the +/- line counts match `git diff --numstat` for
  ordinary text changes but may differ for renames, binary files, or unusual
  context. Verification does not depend on these counts; only trust-mode
  `diff_constraint` scoring does. Snapshots are text-only (binary/oversized files
  are skipped), and verify runs the test command under the tool output/time caps
  but **not** the sandbox path/command policy (it is this runtime's own
  materialisation, not an untrusted agent).
- **Hygiene secret detection is heuristic.** It uses high-precision patterns
  that favor avoiding false positives over catching every secret, so it can miss
  novel or obfuscated credentials. It is not a guarantee that no secret can be
  committed, and it does not detect non-secret sensitive data.
- **Hygiene scope is tracked files.** By default only `git ls-files` content is
  scanned; gitignored-but-present files are ignored on purpose, and bare
  `env`/`ENV` directories are not treated as virtualenvs (to avoid false
  positives). Use `--include-untracked` to widen scope.
- **Model integration is optional and opt-in.** The `llm` adapter exists, but the
  default path is offline (fake client) and no test or committed result makes a
  paid call. A real Claude run requires the `[claude]` extra, an API key, and an
  explicit budget; the real `ClaudeAPIClient` is only constructed on `--allow-paid`.
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
- `src/code_agent_runtime/agents/llm/` (client, pricing, budget, cache, protocol, agent, claude_client)
- `src/code_agent_runtime/importers/` (schema, diffs, sources, convert)
- `src/code_agent_runtime/hygiene.py`, `src/code_agent_runtime/environment.py`
