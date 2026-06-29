# Commit note — Milestone 3

**Commit message:** `Implement structured tool registry and core tools`

## What this commit adds

- `src/code_agent_runtime/tools/` — the tool layer:
  - `base.py`: `Tool`, `ToolContext`, `ToolResult`, `ToolSpec`, `ToolParam`,
    `ToolError`, `TOOL_CATEGORIES`, and workspace path confinement.
  - Seven tools: `read_file`, `write_file`, `apply_patch`, `run_shell`,
    `git_diff`, `run_tests`, `search_repo`.
  - `_exec.py`: shared no-shell subprocess wrapper (bounded output + timeout).
  - `registry.py`: `ToolRegistry`, `ToolCall`, `build_registry`,
    `REGISTERED_TOOL_NAMES`.
- CLI: `tools list` / `tools show`; `info` now reports Milestone 3.
- Tests: `tests/test_tools.py` (unit + integration over the `tiny_python_bug`
  fixture); `tests/test_scaffold_layout.py` extended for the Milestone 3 notes.
- Docs/site: `site/architecture.html` (tools implemented, Core tools section),
  `site/task-format.html`, `site/index.html`, `site/roadmap.html` updated;
  `docs/ARCHITECTURE.md` status updated.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts.
Tools run subprocesses with `shell=False` and confine file access to the
workspace; this is a baseline guard, **not** the full sandbox (Milestone 7). No
new runtime dependency is added — the patch applier is pure Python and `git_diff`
shells to the already-required `git`.

## Verification at commit time

- `python3 -m pytest -q` passes (134+ tests; git-dependent tool tests skip if
  `git` is unavailable).
- `PYTHONPATH=src python3 -m code_agent_runtime tools list` lists seven tools.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
