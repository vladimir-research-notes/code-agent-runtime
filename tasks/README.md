# Tasks

Versioned, declarative coding-agent task definitions (Milestone 2). Each task is
a small file describing **one** unit of work: what to do, which fixture repo to
do it in, which tools are allowed, and how success is judged. Tasks are *data* —
loading one runs no agent and executes no command. The runtime that consumes
them is built in later milestones (see [`../docs/PLAN.md`](../docs/PLAN.md)).

## Format

- **Canonical:** JSON, named `*.task.json`.
- **Optional:** YAML (`*.task.yaml` / `*.task.yml`), parsed only when PyYAML is
  installed. Keeping JSON canonical lets the core package and default tests stay
  dependency-free.

A loader (`code_agent_runtime.tasks`) parses, validates, and resolves the
`fixture` path. Invalid tasks fail with a readable list of problems naming each
offending field.

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `version` | yes | Schema version (currently `1`). |
| `id` | yes | Stable identity, lowercase, `-`/`_`/`.`/`/` separators. |
| `title` | yes | Short human-readable name. |
| `prompt` | yes | Instruction given to the agent. |
| `fixture` | yes | Path to the workspace snapshot, relative to the task file. |
| `scoring_method` | yes | One of `test_command`, `expected_files`, `diff_constraint`, `custom`, `none`. |
| `allowed_tools` | no | Subset of the tool registry the agent may use. |
| `timeout_seconds` | no | Wall-clock budget (default 300). |
| `test_command` | conditionally | Required when `scoring_method` is `test_command`; a shell string or argv list. |
| `resource_limits` | no | `cpu_seconds`, `memory_mb`, `max_output_bytes`, `network`. |
| `metadata` | no | Free-form tags (category, language, difficulty, ...). |

## Example tasks

| Task | Kind | Fixture |
| --- | --- | --- |
| `bugfix/sum-range-off-by-one` | bug fix | `examples/tiny_python_bug` |
| `cli/add-shout-flag` | CLI behaviour change | `examples/tiny_cli_project` |
| `security/unsafe-command-demo` | sandbox-policy probe | `examples/unsafe_command_demo` |

## Inspecting tasks

```bash
PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks
PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks
```
