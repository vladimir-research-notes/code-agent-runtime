Human review: Milestone 7 — Permission policies and sandbox controls

TL;DR
Adds a `sandbox/` policy layer over the tools. `SandboxPolicy` declares
allowed/denied read & write path globs, a command allow/denylist, a network flag,
and runtime/output caps; `Sandbox.check_call` gates each *agent* tool call before
it runs (a denied call never executes) and `Sandbox.redact_result` scrubs
credential-shaped output afterwards, reusing the hygiene scanner's secret
patterns. Enforcement is on by default in `run_task` (`RunConfig.enforce_sandbox`)
with permissive, task-derived defaults, so the scripted bugfix/CLI runs still
pass. A new adversarial `probe` agent drives the unsafe-command demo and the
sandbox blocks every host-escaping action. Covered by `tests/test_sandbox.py`
(41 tests); the full suite passes.

What changed
- Added `src/code_agent_runtime/sandbox/` (`policy.py`, `permissions.py`,
  `secret_scanner.py`, `__init__.py`).
- Added `tools/apply_patch.py::patch_target_paths`.
- Wired the sandbox into the runtime: `RunConfig.enforce_sandbox`,
  `RunResult.policy`, `dispatch_agent_call(..., sandbox=)`,
  `make_context(..., policy=)`, `run_task(..., policy=)`, `format_run_report`.
- Added `agents/probes.py` (unsafe probe; separate from `SOLUTIONS`).
- CLI: `run --agent probe`, `run --no-sandbox`; `info` reports Milestone 7.
- `security/unsafe-command-demo` task now allows `write_file`.
- Added `tests/test_sandbox.py`; extended `tests/test_scaffold_layout.py`.
- Updated `docs/SECURITY_MODEL.md`, `docs/LIMITATIONS.md`, `docs/ARCHITECTURE.md`,
  `README.md`, and the website (sandboxing, security, index, architecture,
  limitations, roadmap, tracing-replay).

What should be checked later
- Default policy choices. Confirm the default `denied_paths` (`.env`, `.git`,
  `.aws`, `.ssh`, `*.pem`, `*.key`, …) and `command_denylist` (`rm`, `sudo`, `dd`,
  `shutdown`, …) match your intent, and that the *omissions* are deliberate:
  ordinary build/test programs (`python3`, `pytest`, `node`, `git`, `make`) are
  intentionally allowed so normal runs work. Network programs (`curl`, `wget`,
  `ssh`, …) are gated by the `network` flag, not the denylist, so a task that opts
  into the network can still use them.
- Enforced-by-default. `run_task` enforces the sandbox unless
  `RunConfig.enforce_sandbox=False` (CLI `--no-sandbox`). Confirm on-by-default is
  what you want; the permissive defaults are tuned so the shipped solutions pass.
- Two-layer gating semantics. A blocked call (either `allowed_tools` *or* policy)
  is recorded as category `"blocked"`, `allowed=False`, with the policy rule in
  `result.data['policy_rule']`. Replay/reports already treat `allowed=False` as a
  blocked anomaly, so policy blocks show up the same way as capability blocks.
- Redaction scope. `Sandbox.redact_result` scrubs `content`/`stdout`/`stderr`/`diff`
  plus the summary/error and records `redacted_secret_count`. It also runs on the
  runtime-issued `run_tests`/`git_diff` output (those are not policy-gated, but
  their output is scrubbed). Confirm this is the right boundary and that redacting
  what the agent *reads* (its next observation) is desired (it is, to avoid feeding
  secrets to a future model agent).
- Honest scope. This is **not** a jail: command matching is by program name (a
  renamed binary / absolute path to a copy is not caught); network enforcement is
  a heuristic denylist (a direct `socket` open is not blocked); there is no
  process/namespace isolation (a containerised runner is a non-goal here);
  `cpu_seconds` is enforced as wall-clock. Confirm `docs/SECURITY_MODEL.md` states
  these plainly enough.
- No destructive execution in tests. The probe's `rm -rf .` / `curl` steps are
  blocked before dispatch, and the probe is only ever run with the sandbox on, so
  nothing destructive runs. Confirm you are comfortable with the probe shipping in
  the repo (it is data — a fixed script — not an executed command).

Technical risks
- Low–moderate. No new dependency; the policy is pure data and the enforcer is
  pure functions. The main risk is a *false sense of security* from the word
  "sandbox" — mitigated by the explicit non-jail framing in the docs and the
  `summary_line`/`policy` echo so a reviewer can see exactly what was enforced.
  Secondary: the `_path_matches` heuristic (exact / basename glob / directory
  segment) is intentionally simple; confirm it does not over- or under-match for
  your real policies (it is covered by a parametrised test).

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_sandbox.py -q`
- `PYTHONPATH=src python3 -m code_agent_runtime run security/unsafe-command-demo --agent probe`
- `PYTHONPATH=src python3 -m code_agent_runtime run security/unsafe-command-demo --agent probe --json`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --no-sandbox`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
