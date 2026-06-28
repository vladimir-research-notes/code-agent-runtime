# Security model

> **Status:** threat model documented; **repository hygiene scanning implemented
> (Milestone 1)**. Runtime containment primitives (path/command policies, network
> flag, runtime/output caps) still arrive in Milestone 7. This document is
> explicit about what is and is not yet implemented or proven.

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

## Planned controls (Milestone 7)

- Allowed read paths / allowed write paths / denied paths.
- Command allowlist and denylist.
- Network policy flag (default: no network).
- Max runtime and max output size.
- Secret scanner over inputs, outputs, and traces.
- Optional containerized runner (`docker_runner.py`) for stronger isolation.

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
- [ ] Runtime containment primitives (paths, commands, network, caps) — Milestone 7.

## Relevant files

- `src/code_agent_runtime/hygiene.py`, `src/code_agent_runtime/environment.py`
- `scripts/00_check_environment.py`, `scripts/04_check_repo_hygiene.py`
- `.gitignore`, `.claude/settings.json` (repo-level guards)
- `docs/LIMITATIONS.md`, `docs/PLAN.md`

## Open questions

- How much isolation can be achieved without containers or root?
- What is the right default network posture for scripted vs. LLM agents?
