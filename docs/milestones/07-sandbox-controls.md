# Milestone 7 — Permission policies and sandbox controls

## Summary

Add the **policy layer** over the tools' mechanism: a declarative
`SandboxPolicy` and a `Sandbox` enforcer that gates every *agent* tool call
before it runs and redacts credential-shaped output afterwards. Enforcement is on
by default in the runtime loop (`RunConfig.enforce_sandbox`), with permissive,
task-derived defaults so existing runs are unchanged — the scripted bugfix/CLI
solutions still pass with the sandbox active.

This closes two limitations carried since earlier milestones: there was no
runtime containment beyond workspace confinement + `allowed_tools`, and traces
were stored unredacted. Both are now addressed (honestly scoped — see below).

## Deliverables

- `src/code_agent_runtime/sandbox/policy.py`:
  - `SandboxPolicy` (frozen): allowed/denied read & write path globs, command
    allow/denylist, `network` flag, `max_runtime_seconds`, `max_output_bytes`,
    `redact_secrets`. `from_task` derives the network flag and output/runtime caps
    from a task's `resource_limits`; `to_dict`/`summary_line` for echoing.
  - Default vocabularies: `DEFAULT_DENIED_PATHS` (`.env`, `.git`, `.aws`, `.ssh`,
    `*.pem`, `*.key`, …), `DEFAULT_COMMAND_DENYLIST` (`rm`, `sudo`, `dd`,
    `shutdown`, …), `NETWORK_PROGRAMS` (`curl`, `wget`, `ssh`, …).
- `src/code_agent_runtime/sandbox/permissions.py`:
  - `PolicyDecision` (allowed, rule, reason, detail) and `Sandbox` with
    `check_call` (pre-execution allow/deny), `blocked_result` (the structured
    blocked record), and `redact_result` (post-execution scrub).
  - `_path_matches` (exact / basename glob / directory-segment) and program-name
    matching for commands.
- `src/code_agent_runtime/sandbox/secret_scanner.py`:
  - `redact_text` / `count_secrets`, reusing `hygiene.SECRET_PATTERNS` (one source
    of truth with the commit-time scanner) and its placeholder filter.
- `tools/apply_patch.py`: public `patch_target_paths(patch_text)` so the sandbox
  can path-check `apply_patch` targets before applying.
- Runtime wiring:
  - `RunConfig.enforce_sandbox` (default `True`); `RunResult.policy` (the effective
    policy dict, echoed into the result and embedded trace).
  - `dispatch_agent_call(..., sandbox=)` — two-layer gate (`allowed_tools` then
    policy) plus result redaction.
  - `make_context(..., policy=)` — per-command output/time caps from the policy
    (tighter-of with the configured budget).
  - `run_task(..., policy=)` — defaults to `SandboxPolicy.from_task`; redacts the
    runtime-issued test/diff output too.
  - `format_run_report` reports `sandbox: enforced (network …, N blocked)`.
- `agents/probes.py`: the **unsafe probe** agent (`build_unsafe_probe_agent`,
  `has_probe`, `PROBES`) — an adversarial script, kept separate from `SOLUTIONS`.
- CLI: `run --agent probe` and `run --no-sandbox`; `info` now reports Milestone 7.
- Task: `security/unsafe-command-demo` now allows `write_file` so the path policy
  (not `allowed_tools`) is what blocks the outside-workspace writes.
- Tests: `tests/test_sandbox.py` (41 tests); `tests/test_scaffold_layout.py`
  extended for the Milestone 7 notes.

## Containment primitives (vs. the plan's checklist)

| Required primitive | Where |
| --- | --- |
| allowed read paths | `SandboxPolicy.allowed_read_paths` → `_check_path(read)` |
| allowed write paths | `SandboxPolicy.allowed_write_paths` → `_check_path(write)` |
| denied paths | `SandboxPolicy.denied_paths` (default list) → `_check_path` (wins over allow) |
| command allowlist | `SandboxPolicy.command_allowlist` → `_check_command` |
| command denylist | `SandboxPolicy.command_denylist` (default list) → `_check_command` |
| network policy flag | `SandboxPolicy.network` → deny `NETWORK_PROGRAMS` when off |
| max runtime | `SandboxPolicy.max_runtime_seconds` → `ToolContext.timeout_seconds` |
| max output size | `SandboxPolicy.max_output_bytes` → `ToolContext.max_output_bytes` |
| secret scanner | `secret_scanner.redact_text` → `Sandbox.redact_result` over results/traces |

Unsafe examples (all blocked by the probe run): reading `.env`, reading
`~/.aws/credentials`-style paths, reading `/etc/shadow`, writing outside the
workspace, `rm -rf .`, and a `curl` egress.

## Design notes / decisions

- **Policy over mechanism, two layers.** Tools still confine to the workspace
  (Milestone 3); `allowed_tools` is still the capability gate (Milestone 4). The
  sandbox is a *third*, finer layer: it denies sensitive files inside the
  workspace, restricts writes, and gates commands/network. A block at any layer is
  recorded as a `"blocked"` step with the rule in `data['policy_rule']`.
- **Pre-execution gating, not post-hoc.** A denied call never reaches the tool, so
  a blocked `rm`/`curl`/outside-write has no side effect at all.
- **Runtime-issued commands are redacted, not gated.** The loop's own `run_tests`
  / `git_diff` are trusted (not policy-gated) but their output is still scrubbed,
  so a secret a test prints does not land unredacted in the trace.
- **One source of truth for "looks like a secret."** The redactor reuses the
  hygiene scanner's patterns, so the commit-time guard and the runtime redactor
  agree and cannot drift.
- **Probes are not solutions.** The adversarial script lives in `agents/probes.py`
  and is never in `SOLUTIONS`; `has_solution` stays `False` for the demo, so the
  scripted path is unaffected.

## Honest limitations (carried into docs)

- **Not a jail.** Command matching is by program *name* — a renamed binary or an
  absolute path to a copy is not caught. Network enforcement is a *heuristic*
  denylist; a program that opens a socket directly (e.g.
  `python3 -c "import socket…"`) is not blocked. There is **no** process/namespace
  isolation; a containerised runner is a documented non-goal for this milestone.
- **`cpu_seconds` is enforced as a wall-clock bound**, not true CPU time.
- **Redaction is heuristic** (high-precision patterns); it can miss novel or
  obfuscated secrets and does not detect non-secret sensitive data.
- `search_repo` / `git_diff` are not path-gated (they take no caller-supplied path
  and run fixed, safe operations); their output is still redacted.

## Validation

- `python3 -m pytest -q` — all tests pass. `tests/test_sandbox.py` covers the
  policy (defaults, `from_task`, JSON), the path/command matchers, every
  `check_call` rule (denied path, outside-workspace, allow/deny lists, network on
  vs. off, command allow/denylist), the secret scanner (redaction + placeholder
  filter + no-op cases), `dispatch_agent_call` with a sandbox (a denied call does
  not run; an allowed read is redacted), and the **probe run end to end**: each of
  the seven unsafe steps is blocked with the expected rule while the benign read of
  `app.py` succeeds and nothing escapes the workspace.
- `PYTHONPATH=src python3 -m code_agent_runtime run security/unsafe-command-demo --agent probe`
  prints the blocked steps; `--no-sandbox` disables enforcement.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.

## Status

Complete. Next: Milestone 8 — Scoring and evaluation reports.
