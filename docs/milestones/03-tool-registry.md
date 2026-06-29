# Milestone 3 — Tool registry and core tools

## Summary

Implement the structured tools an agent uses to act on a workspace, plus the
registry that exposes and dispatches them. Every tool shares one shape — a static
spec, a validated entry point, and a JSON-serialisable result — so the runtime
(Milestone 4) can dispatch them uniformly and the trace recorder (Milestone 5)
can record them faithfully. All path-taking tools are confined to a single
workspace directory; subprocess-running tools bound their output and time and run
**without a shell**.

## Deliverables

- `src/code_agent_runtime/tools/` package:
  - `base.py` — `Tool`, `ToolContext`, `ToolResult`, `ToolSpec`, `ToolParam`,
    `ToolError`, `TOOL_CATEGORIES`, and workspace path confinement
    (`ToolContext.resolve` / `relpath`).
  - `read_file.py`, `write_file.py`, `apply_patch.py`, `run_shell.py`,
    `git_diff.py`, `run_tests.py`, `search_repo.py` — the seven core tools.
  - `_exec.py` — shared no-shell subprocess wrapper with bounded output/time.
  - `registry.py` — `ToolRegistry`, `ToolCall`, `build_registry`,
    `REGISTERED_TOOL_NAMES`.
  - `__init__.py` — public API re-exports.
- CLI: `tools list` and `tools show` (`src/code_agent_runtime/cli.py`); `info` now
  reports Milestone 3.
- `tests/test_tools.py` (unit + integration); `tests/test_scaffold_layout.py`
  extended to require the Milestone 3 notes.

## The seven tools

| Tool | Category | Returns (in `data`) |
| --- | --- | --- |
| `read_file` | read | content, bytes, lines, binary, truncated |
| `search_repo` | read | matches (path/line/text), match_count, files_searched |
| `git_diff` | read | unified diff, per-file insertions/deletions, untracked |
| `write_file` | write | path, bytes_written, created, existed_before |
| `apply_patch` | write | per-file mode (create/modify/delete), insertions/deletions |
| `run_shell` | exec | argv, exit_code, stdout, stderr, truncated, timed_out |
| `run_tests` | exec | as `run_shell`, plus `passed` (exit 0 and not timed out) |

## Design notes / decisions

- **One shape, structured results.** A tool never returns a bare string and never
  lets an *anticipated* failure escape as an exception. `Tool.run` validates
  arguments against the spec and converts a raised `ToolError` (missing file,
  malformed patch, non-git workspace, path escape) into a failed `ToolResult`
  (`ok=False`). Programmer bugs are *not* swallowed — they propagate so tests
  catch them.
- **No timing in results.** Timestamps and durations belong to the trace recorder
  (Milestone 5); keeping them out of `ToolResult` makes tool outputs
  deterministic and unit-testable.
- **Workspace confinement is a baseline, not the sandbox.** `ToolContext.resolve`
  refuses to read or write outside the workspace root (including via `..` and
  symlinks). This is a usability/safety floor; the full permission policy
  (allow/deny lists, secret scanning, network isolation, process limits) is
  Milestone 7. Documented honestly rather than overclaimed.
- **No shell.** `run_shell`/`run_tests` run an argv list with `shell=False`; a
  string command is `shlex`-split but pipes/redirects/globs/`$VAR` are **not**
  interpreted. Enabling a shell would make injection trivial; the limitation is
  intentional and documented.
- **Pure-Python patch applier.** `apply_patch` parses and applies standard
  unified diffs itself (no `git apply`/`patch` dependency): deterministic, works
  in a non-git workspace, atomic across files, exact-context (no fuzz).
  Limitations: no fuzzy matching, no binary patches, no rename detection.
- **Registry is the source of truth for tool names.** `REGISTERED_TOOL_NAMES`
  must equal the task schema's `KNOWN_TOOLS`; a test asserts this, so drift
  between "tools a task may request" and "tools that exist" fails CI. This
  resolves the open question raised in the Milestone 2 review.

## Validation

- `python3 -m pytest -q` — all tests pass (adds `tests/test_tools.py`: per-tool
  unit tests, confinement, argument validation, registry, CLI, and an
  integration test that fixes the `tiny_python_bug` fixture end-to-end via
  read → search → apply_patch → run_tests). Git-dependent tests skip when `git`
  is absent.
- `PYTHONPATH=src python3 -m code_agent_runtime tools list` — lists the seven
  tools with category and summary.
- `PYTHONPATH=src python3 -m code_agent_runtime tools show apply_patch` — shows a
  tool's parameter spec.
- `python3 scripts/04_check_repo_hygiene.py` — repo stays clean.

## Status

Complete. Next: Milestone 4 — Local runtime state machine.
