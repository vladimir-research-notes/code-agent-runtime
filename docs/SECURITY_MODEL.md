# Security model

> **Status:** skeleton (Milestone 0). This document states the *intended* threat
> model and is explicit about what is **not** yet implemented or proven.
> Containment primitives arrive in Milestone 7.

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

The repository itself is protected by `.claude/settings.local.json`-aware
ignore rules and `.gitignore` entries for secrets, plus the operating
principle that no secrets are committed. Repo hygiene scanning arrives in
Milestone 1.

## Current implementation status

- [ ] None of the runtime containment primitives are implemented yet.
- [x] Documented threat model and non-goals (this file).

## Relevant files

- `.gitignore`, `.claude/settings.json` (repo-level guards)
- `docs/LIMITATIONS.md`, `docs/PLAN.md`

## Open questions

- How much isolation can be achieved without containers or root?
- What is the right default network posture for scripted vs. LLM agents?
