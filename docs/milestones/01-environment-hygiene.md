# Milestone 1 — Environment and repository hygiene

## Summary

Add two operational checks that gate the project's CPU-only, no-paid-API and
no-committed-junk operating principles:

1. an **environment check** that verifies the host can build and test the
   runtime offline; and
2. a **repository hygiene scanner** that inspects version-controlled files for
   secrets, virtualenvs, caches, `node_modules`, large files, result blobs,
   model weights, and a committed local Claude settings file.

Both are read-only, deterministic, dependency-free, and offline.

## Deliverables

- `src/code_agent_runtime/environment.py` — structured environment checks
  (`run_environment_checks`, `EnvironmentReport`, `format_report`, `main`).
- `src/code_agent_runtime/hygiene.py` — `scan_repo`, `HygieneReport`,
  `HygieneFinding`, secret/dir/extension rules, text/JSON output, `main`.
- CLI subcommands `env-check` and `hygiene` (`src/code_agent_runtime/cli.py`).
- `scripts/00_check_environment.py`, `scripts/04_check_repo_hygiene.py` — thin,
  install-free wrappers matching the planned `scripts/` layout.
- `tests/test_environment.py`, `tests/test_hygiene.py` — CPU-only tests,
  including a guard that scans the real repo and asserts it is clean.

## Design notes / decisions

- **Scope = tracked files.** Hygiene is about what is *in version control*, so
  by default the scanner reads `git ls-files` and ignores gitignored-but-present
  junk (a local `.venv`, caches). Outside a git work tree it falls back to a
  filesystem walk. `--include-untracked` widens scope to non-ignored untracked
  files.
- **Directory-level dedup.** `node_modules`, `__pycache__`, and `.venv` are
  reported once per offending directory rather than once per contained file.
- **Honest secret detection.** Patterns are high-precision (AWS keys, private-key
  blocks, provider API-key shapes, plus a heuristic `key = <16+ chars>`
  assignment rule with a placeholder filter). It is best-effort, not a
  guarantee; an inline `# hygiene: ignore` silences a line. Test fixtures build
  secret-shaped strings by concatenation so this repo's own source stays clean.
- **Severities.** Secrets, virtualenvs, weights, and a committed
  `.claude/settings.local.json` are errors (non-zero exit). Caches,
  `node_modules`, large files, and result blobs are warnings (`--strict`
  promotes them to failures).

## Validation

- `python3 -m pytest -q` — all tests pass.
- `python3 scripts/00_check_environment.py` — environment check runs (PASS here).
- `python3 scripts/04_check_repo_hygiene.py` — hygiene scan runs; repo is clean.
- `PYTHONPATH=src python3 -m code_agent_runtime env-check` / `... hygiene`.

## Status

Complete. Next: Milestone 2 — Versioned task format.
