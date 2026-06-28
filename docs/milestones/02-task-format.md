# Milestone 2 — Versioned task format

## Summary

Define the on-disk contract for a coding-agent *task*: a small, versioned,
declarative file describing one unit of work — what to do, where, with which
tools, under what limits, and how success is judged. This milestone adds the
schema, a loader with strict and readable validation, fixture-path resolution,
three example tasks with real fixtures, and CLI commands to list and inspect
tasks. Tasks are **data only**; nothing here runs an agent or executes a command.

## Deliverables

- `src/code_agent_runtime/tasks/` package:
  - `schema.py` — `Task`, `ResourceLimits`, `TaskValidationError`,
    `validate_task_dict`, and the closed vocabularies `KNOWN_TOOLS`,
    `SCORING_METHODS`, `SCHEMA_VERSION`/`SUPPORTED_VERSIONS`.
  - `loader.py` — `load_task`, `parse_task_text`, `discover_task_files`,
    `discover_tasks`, `find_task` (JSON canonical; optional YAML).
  - `fixtures.py` — `resolve_fixture`, `fixture_exists`, `check_fixture`.
  - `__init__.py` — public API re-exports.
- Example fixtures under `examples/`: `tiny_python_bug`, `tiny_cli_project`,
  `unsafe_command_demo`.
- Example tasks under `tasks/`: `bugfix/sum-range-off-by-one`,
  `cli/add-shout-flag`, `security/unsafe-command-demo`, plus `tasks/README.md`.
- CLI: `tasks list` and `tasks show` (`src/code_agent_runtime/cli.py`); `info`
  now reports Milestone 2.
- `tests/test_tasks.py`; `tests/test_scaffold_layout.py` extended to require the
  Milestone 2 notes.

## Design notes / decisions

- **JSON is canonical; YAML is optional.** Example tasks and the default test
  path use `*.task.json`, keeping the core package dependency-free and tests
  free/offline. `*.task.yaml`/`.yml` are parsed only when PyYAML is importable;
  a missing PyYAML yields a clear, actionable error, not an import traceback.
- **Validation collects all problems.** `validate_task_dict` aggregates every
  issue (unknown fields, missing required fields, bad types, unknown tools,
  unrecognised scoring methods, unsupported versions, bad limits) into one
  `TaskValidationError` that renders a readable, source-named, multi-line
  message — so an author fixes everything in one pass.
- **Closed vocabularies.** `allowed_tools` is checked against the seven tools the
  registry will expose (Milestone 3); `scoring_method` against the five methods
  scoring will implement (Milestone 8). Typos fail at authoring time.
- **Schema vs. resolution are separable.** Schema validation is pure (no
  filesystem). Fixture existence is a separate, opt-in check
  (`load_task(resolve_fixture=...)`), so tasks can be authored before fixtures
  exist and `tasks list` can report fixture presence without hard-failing.
- **`test_command` accepts a shell string or an argv list**, normalised to argv;
  required only when `scoring_method == "test_command"`.

## Validation

- `python3 -m pytest -q` — all tests pass (adds `tests/test_tasks.py`).
- `PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks` — lists
  the three example tasks; each fixture resolves.
- `PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks`.
- `python3 scripts/04_check_repo_hygiene.py` — repo stays clean.

## Status

Complete. Next: Milestone 3 — Tool registry and core tools.
