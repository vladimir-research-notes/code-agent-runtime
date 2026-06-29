# Security model

> **Status:** threat model documented; **repository hygiene scanning implemented
> (Milestone 1)** and **runtime containment primitives implemented (Milestone 7)** —
> path/command/network policy, runtime/output caps, and a secret scanner, enforced
> on every agent tool call by default. This document is explicit about what is and
> is not enforced or proven; the controls reduce blast radius and add observability,
> they are not a jail.

## Honest framing

This project is **not a production-grade sandbox.** A capable adversary, or an
agent running with broad host permissions, can escape the controls described
here. The goal is *blast-radius reduction* and *observability* for
semi-trusted, deterministic agents on a developer machine — not isolation of
malicious code.

## Assets to protect

- Developer secrets (`.env`, `~/.aws`, `~/.ssh`, cloud credentials).
- Files outside the designated workspace.
- The network (egress / exfiltration).
- The host from destructive shell commands.

## Threat actors (in scope)

- A buggy or over-eager agent that reads or writes outside its workspace.
- A scripted/LLM agent that runs a dangerous shell command by mistake.
- Accidental secret capture into traces or reports.

## Out of scope

- A deliberately malicious agent with native code execution and kernel exploits.
- Side-channel attacks, timing attacks, hardware attacks.
- Multi-tenant isolation guarantees.

## Runtime containment controls (Milestone 7)

The `code_agent_runtime.sandbox` package implements a declarative `SandboxPolicy`
and a `Sandbox` enforcer. The runtime loop builds a policy per run (default:
`SandboxPolicy.from_task`) and, when `RunConfig.enforce_sandbox` is on (the
default), gates every **agent** tool call against it and redacts the result. The
effective policy is echoed into the `RunResult` (and the embedded trace) so a run
records exactly what was allowed and blocked.

- **Allowed / denied read & write paths.** Workspace-relative glob patterns checked
  per call (`read_file`, `write_file`, and `apply_patch`'s parsed targets). The
  default `denied_paths` protects `.env`, `.git`, `.aws`, `.ssh`, `*.pem`, `*.key`,
  `credentials`, and similar; `denied_paths` always wins over an allow rule. An
  out-of-workspace path is denied with rule `outside_workspace` (the tool's own
  confinement is the second layer).
- **Command allowlist / denylist.** Matched by program name (`argv[0]` basename).
  The default denylist blocks clearly host-destructive commands (`rm`, `sudo`,
  `dd`, `shutdown`, …); ordinary build/test programs are allowed.
- **Network policy flag** (default: off). Enforced *heuristically* by denying
  well-known network programs (`curl`, `wget`, `ssh`, …) when off.
- **Max runtime and max output size.** Wall-clock and byte caps applied through the
  `ToolContext` (`cpu_seconds` from a task is used as the wall-clock bound).
- **Secret scanner over outputs and traces.** Credential-shaped strings in file
  contents, stdout/stderr, and diffs are redacted before they enter a step, a
  trace, or the agent's next observation — reusing the hygiene scanner's patterns.

### What is NOT enforced (honest limits)

This is **not** a production-grade sandbox:

- Command matching is by program *name* — a renamed binary, or an absolute path to
  a copy of a denied program, is not caught.
- Network enforcement is a heuristic denylist; a program that opens a socket
  directly (e.g. `python3 -c "import socket; ..."`) is **not** blocked.
- There is **no process or namespace isolation** and no resource cgroup. A
  containerized runner (`docker_runner.py`) for stronger isolation remains an
  optional, future capability — a documented non-goal for this milestone.
- `cpu_seconds` is enforced as a wall-clock bound, not true CPU time.
- Redaction is heuristic (high-precision patterns); it can miss novel or obfuscated
  secrets and does not detect non-secret sensitive data.

## Defense-in-depth today

The repository itself is protected by `.gitignore` rules (secrets, venvs,
caches, weights), `.claude/settings.json` deny rules, the operating principle
that no secrets are committed, and — as of Milestone 1 — an automated
**repository hygiene scanner**.

### Repository hygiene scanner (Milestone 1)

`code_agent_runtime.hygiene` scans the files actually under version control
(`git ls-files`; filesystem-walk fallback) and flags:

- **secrets** — AWS keys, private-key blocks, provider API-key shapes, and a
  heuristic `key = <16+ chars>` assignment rule with a placeholder filter
  (errors);
- **virtualenvs** — `.venv`/`venv` trees and `pyvenv.cfg` markers (errors);
- **model weights** — `*.safetensors`, `*.gguf`, `*.pt`, ... (errors);
- **committed `.claude/settings.local.json`** (error);
- **caches**, **`node_modules`**, **large files**, **result blobs** (warnings;
  `--strict` promotes them to failures).

This is a *commit-hygiene* guard, not a runtime control, and secret detection is
**best-effort and heuristic** — high-precision patterns that favor avoiding
false positives over catching every possible secret. It is not a guarantee that
no secret can ever be committed. An inline `# hygiene: ignore` suppresses a line.
Run it with `python3 scripts/04_check_repo_hygiene.py` or
`code-agent-runtime hygiene`.

## Current implementation status

- [x] Documented threat model and non-goals (this file).
- [x] Repository hygiene scanner over tracked files (Milestone 1).
- [x] Environment check (offline, CPU-only policy) (Milestone 1).
- [x] Runtime containment primitives (paths, commands, network, caps, secret
      redaction), enforced by default (Milestone 7).
- [ ] Containerized runner for stronger isolation — future, optional.

## Demonstration

The built-in `probe` agent attempts the unsafe actions above against
`security/unsafe-command-demo`; the sandbox blocks every one while allowing a
benign in-workspace read:

```
code-agent-runtime run security/unsafe-command-demo --agent probe
```

`tests/test_sandbox.py` asserts each block (and its rule) and the benign allow.

## Relevant files

- `src/code_agent_runtime/sandbox/` (`policy.py`, `permissions.py`, `secret_scanner.py`)
- `src/code_agent_runtime/runtime/execution.py`, `runtime/agent_loop.py` (enforcement)
- `src/code_agent_runtime/agents/probes.py` (the unsafe probe agent)
- `src/code_agent_runtime/hygiene.py`, `src/code_agent_runtime/environment.py`
- `scripts/00_check_environment.py`, `scripts/04_check_repo_hygiene.py`
- `.gitignore`, `.claude/settings.json` (repo-level guards)
- `tests/test_sandbox.py`, `docs/LIMITATIONS.md`, `docs/PLAN.md`

## Open questions

- How much stronger isolation can be achieved without containers or root?
- What is the right default network posture for scripted vs. LLM agents?
- Should the command policy move from program-name matching to an
  executed-path/hash allowlist?
