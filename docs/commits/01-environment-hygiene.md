# Commit note — Milestone 1

**Commit message:** `Add environment and repository hygiene checks`

## What this commit adds

- `src/code_agent_runtime/environment.py` — read-only environment check
  (Python version, git, pytest, platform, git work-tree, offline policy) with
  text and JSON output and an exit code gated on required checks.
- `src/code_agent_runtime/hygiene.py` — repository hygiene scanner over
  git-tracked files (filesystem-walk fallback) detecting secrets, virtualenvs,
  caches, `node_modules`, large files, result blobs, model weights, and a
  committed `.claude/settings.local.json`.
- CLI: new `env-check` and `hygiene` subcommands; `info` now reports
  Milestone 1.
- `scripts/00_check_environment.py`, `scripts/04_check_repo_hygiene.py` —
  install-free wrappers.
- Tests: `tests/test_environment.py`, `tests/test_hygiene.py`; extended
  `tests/test_scaffold_layout.py` to require the Milestone 1 notes.
- Docs/site: README, `SECURITY_MODEL.md`, `REPRODUCIBILITY.md`,
  `LIMITATIONS.md`, and `site/{index,security,sandboxing}.html` updated.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts.
Secret-shaped test fixtures are assembled at runtime so the tracked source never
contains a contiguous credential; the hygiene scanner asserts the repo is clean.

## Verification at commit time

- `python3 -m pytest -q` passes.
- `python3 scripts/00_check_environment.py` reports PASS.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
