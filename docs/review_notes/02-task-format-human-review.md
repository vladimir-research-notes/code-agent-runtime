Human review: Milestone 2 — Versioned task format

TL;DR
Adds the declarative, versioned task format: a `tasks/` package (schema, loader,
fixture resolution), three example tasks with real `examples/` fixtures, and
`tasks list` / `tasks show` CLI commands. Tasks are data only — nothing executes
an agent or a command yet. JSON is canonical; YAML is optional (PyYAML stays an
optional, non-test dependency). Validation collects all problems into one
readable, source-named error. Covered by `tests/test_tasks.py`.

What changed
- Added `src/code_agent_runtime/tasks/{schema,loader,fixtures,__init__}.py`.
- Added `examples/{tiny_python_bug,tiny_cli_project,unsafe_command_demo}/`.
- Added `tasks/{bugfix,cli,security}/*.task.json` and `tasks/README.md`.
- Added CLI `tasks list` / `tasks show`; `info` now reports Milestone 2.
- Added `tests/test_tasks.py`; extended `tests/test_scaffold_layout.py`.
- Updated `site/task-format.html`, `site/index.html`, `docs/ARCHITECTURE.md`,
  and `README.md`.

What should be checked later
- Field set and naming. Confirm `version/id/title/prompt/fixture/allowed_tools/
  timeout_seconds/scoring_method/test_command/resource_limits/metadata` is the
  right surface, and that `scoring_method` values
  (`test_command/expected_files/diff_constraint/custom/none`) match what
  Milestone 8 scoring will actually implement.
- `KNOWN_TOOLS` is hard-coded here and must stay in sync with the Milestone 3
  tool registry; decide whether the registry should become the single source of
  truth and the schema import from it.
- Fixture resolution is relative to the task file's directory. Confirm this is
  the desired convention versus repo-root-relative; check the `../../examples/...`
  paths in the shipped tasks.
- Whether unknown top-level fields should be a hard error (current behaviour) or
  a warning, to allow forward-compatible additions.
- The `security/unsafe-command-demo` task uses `scoring_method: none` and is
  judged manually; its real enforcement lands in Milestone 7. Confirm the
  prompt's described unsafe actions match the policy you intend to test.

Technical risks
- Low. All new code is pure data parsing/validation; no execution, no network,
  no filesystem writes. The only filesystem reads are task files and fixture
  existence checks. Secret detection / hygiene unaffected (repo-clean guard
  still passes).
- YAML support depends on PyYAML; absence is handled with a clear error and the
  YAML test is skipped when PyYAML is missing.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks`
- `PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks --json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
