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
| `scoring_config` | conditionally | Method-specific scoring parameters (Milestone 8); see below. |
| `resource_limits` | no | `cpu_seconds`, `memory_mb`, `max_output_bytes`, `network`. |
| `metadata` | no | Free-form tags (category, language, difficulty, ...). |

### `scoring_config` by method (Milestone 8)

| `scoring_method` | `scoring_config` keys |
| --- | --- |
| `test_command` | _(none; uses `test_command`)_ |
| `expected_files` | `present` (paths must exist), `absent` (must not exist), `contains` (list of `{path, text}`; `text` is a string or list of strings) — at least one required. |
| `diff_constraint` | `allowed_paths` (required globs the change may touch), `forbidden_paths`, `max_files`, `allow_empty` (default `false`). |
| `custom` | `name` (required; a scorer in the in-code registry) plus any params it reads, e.g. `allowed_paths` for `tests_pass_and_diff_scope`. |
| `none` | _(not auto-scored)_ |

Globs match with `fnmatch` against the workspace-relative path and its basename
(`*` spans `/`). Diff-scope analysis ignores Python bytecode caches
(`__pycache__`, `*.pyc`).

## Example tasks

The 13 tasks below make up the Milestone 12 **reproducible case study** — small
but genuine work spanning every category, each with a deterministic scripted
solution (or, for the security demos, a sandbox probe). See
[`../docs/RESULTS.md`](../docs/RESULTS.md) for the full result matrix.

| Task | Category | Scoring method | Fixture |
| --- | --- | --- | --- |
| `bugfix/sum-range-off-by-one` | bugfix | `test_command` | `examples/tiny_python_bug` |
| `bugfix/sum-range-expected-files` | bugfix | `expected_files` | `examples/tiny_python_bug` |
| `bugfix/temp-convert-ratio` | bugfix | `test_command` | `examples/temperature` |
| `bugfix/gcd-modulo-swap` | bugfix | `test_command` | `examples/number_theory` |
| `refactor/sum-range-diff-scope` | refactor | `diff_constraint` | `examples/tiny_python_bug` |
| `refactor/extract-rate-constant` | refactor | `custom` | `examples/refactor_pricing` |
| `cli/add-shout-flag` | cli_change | `test_command` | `examples/tiny_cli_project` |
| `cli/add-shout-flag-custom` | cli_change | `custom` | `examples/tiny_cli_project` |
| `cli/add-reverse-flag` | cli_change | `test_command` | `examples/cli_echo` |
| `tests/implement-slugify` | tests_must_pass | `test_command` | `examples/text_utils` |
| `tests/implement-kv-parser` | tests_must_pass | `test_command` | `examples/kv_parser` |
| `security/unsafe-command-demo` | security | `none` (sandbox probe) | `examples/unsafe_command_demo` |
| `security/secret-read-demo` | security | `none` (sandbox probe) | `examples/secret_demo` |

## Inspecting tasks

```bash
PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks
PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks
```

## Running and scoring tasks

```bash
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one
PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks   # score the whole suite
```
