# Commit note — Milestone 2

**Commit message:** `Add versioned coding-agent task format`

## What this commit adds

- `src/code_agent_runtime/tasks/` — task schema, loader, and fixture resolution:
  - `schema.py`: `Task`, `ResourceLimits`, `TaskValidationError`,
    `validate_task_dict`, and vocabularies (`KNOWN_TOOLS`, `SCORING_METHODS`,
    `SCHEMA_VERSION`).
  - `loader.py`: `load_task`, `parse_task_text`, `discover_task_files`,
    `discover_tasks`, `find_task` (JSON canonical; optional YAML via PyYAML).
  - `fixtures.py`: `resolve_fixture`, `fixture_exists`, `check_fixture`.
- `examples/` fixtures: `tiny_python_bug`, `tiny_cli_project`,
  `unsafe_command_demo`.
- `tasks/` definitions: `bugfix/sum-range-off-by-one`, `cli/add-shout-flag`,
  `security/unsafe-command-demo`, plus `tasks/README.md`.
- CLI: `tasks list` / `tasks show`; `info` now reports Milestone 2.
- Tests: `tests/test_tasks.py`; `tests/test_scaffold_layout.py` extended.
- Docs/site: `site/task-format.html` and `site/index.html` updated,
  `docs/ARCHITECTURE.md` status updated, README updated.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts.
The `unsafe_command_demo` fixture references credential *paths* the sandbox must
protect (e.g. `~/.aws/credentials`) but contains no real secrets; the hygiene
scanner asserts the repo is clean. PyYAML is not added as a dependency — it stays
optional and the canonical task format is JSON so default tests need no install.

## Verification at commit time

- `python3 -m pytest -q` passes.
- `PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks` lists the
  three example tasks with resolvable fixtures.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
