# Commit note — Milestone 7

**Commit message:** `Add permission policies and sandbox controls`

## What this commit adds

- `src/code_agent_runtime/sandbox/` — the policy layer over the tools:
  - `policy.py` — `SandboxPolicy` (allowed/denied read & write path globs, command
    allow/denylist, `network`, `max_runtime_seconds`, `max_output_bytes`,
    `redact_secrets`), `from_task`, `to_dict`, `summary_line`, and the default
    vocabularies (`DEFAULT_DENIED_PATHS`, `DEFAULT_COMMAND_DENYLIST`,
    `NETWORK_PROGRAMS`).
  - `permissions.py` — `Sandbox` (`check_call` pre-execution gate, `blocked_result`,
    `redact_result` post-execution scrub), `PolicyDecision`, path/command matchers.
  - `secret_scanner.py` — `redact_text` / `count_secrets`, reusing the hygiene
    scanner's `SECRET_PATTERNS` (single source of truth).
- `tools/apply_patch.py` — public `patch_target_paths` so the sandbox can
  path-check patch targets before applying.
- Runtime wiring: `RunConfig.enforce_sandbox` (default on), `RunResult.policy`,
  `dispatch_agent_call(..., sandbox=)` (two-layer gate + redaction),
  `make_context(..., policy=)` (output/time caps), `run_task(..., policy=)`
  (defaults to `SandboxPolicy.from_task`; redacts runtime test/diff output),
  `format_run_report` reports the sandbox line.
- `agents/probes.py` — the unsafe probe agent (separate from `SOLUTIONS`).
- CLI: `run --agent probe`, `run --no-sandbox`; `info` reports Milestone 7.
- Task: `security/unsafe-command-demo` allows `write_file` so the path policy
  blocks the outside-workspace writes.
- Tests: `tests/test_sandbox.py`; `tests/test_scaffold_layout.py` extended.
- Docs/site: `sandboxing.html` and `security.html` (now implemented),
  `index.html`, `architecture.html`, `limitations.html`, `roadmap.html`,
  `tracing-replay.html` (redaction note), `docs/SECURITY_MODEL.md`,
  `docs/LIMITATIONS.md`, `docs/ARCHITECTURE.md`, `README.md`; Milestone 7
  milestone/commit/review notes added.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (the sandbox uses only the stdlib + existing modules). No
paid API. **No destructive command is ever executed**: the probe's `rm`/`curl`
steps are blocked *before* dispatch, and the probe is only run with the sandbox
on. The committed `unsafe_command_demo` fixture contains no real secrets — the
credential paths it references are targets the sandbox must protect, never values.

## Honesty notes

This is **not** a production-grade sandbox. Command matching is by program name;
network enforcement is a heuristic denylist (a direct socket open is not blocked);
there is no process/namespace isolation (a containerised runner is a non-goal for
this milestone). `cpu_seconds` is enforced as a wall-clock bound. Secret redaction
is heuristic and shares the hygiene scanner's high-precision patterns. These are
documented in `docs/SECURITY_MODEL.md` and `docs/LIMITATIONS.md`.

## Verification at commit time

- `python3 -m pytest -q` passes (git-dependent diff assertions skip if `git` is
  unavailable).
- `PYTHONPATH=src python3 -m code_agent_runtime run security/unsafe-command-demo --agent probe`
  blocks every unsafe step (denied paths, outside-workspace writes, `rm`, `curl`)
  while allowing the benign read of `app.py`.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
