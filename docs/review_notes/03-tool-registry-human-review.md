Human review: Milestone 3 — Tool registry and core tools

TL;DR
Adds the tool layer an agent uses to act on a workspace: seven structured tools
(`read_file`, `write_file`, `apply_patch`, `run_shell`, `git_diff`, `run_tests`,
`search_repo`), a uniform `Tool`/`ToolContext`/`ToolResult` shape, and a
`ToolRegistry` that dispatches `ToolCall`s. Every tool returns a JSON-serialisable
result for tracing, validates its arguments against a declared spec, and confines
file access to the workspace. Subprocess tools run without a shell and bound their
output and time. Covered by `tests/test_tools.py`, including an end-to-end
integration test that fixes the `tiny_python_bug` fixture.

What changed
- Added `src/code_agent_runtime/tools/` (`base`, `read_file`, `write_file`,
  `apply_patch`, `run_shell`, `git_diff`, `run_tests`, `search_repo`, `_exec`,
  `registry`, `__init__`).
- Added CLI `tools list` / `tools show`; `info` now reports Milestone 3.
- Added `tests/test_tools.py`; extended `tests/test_scaffold_layout.py`.
- Updated `site/architecture.html`, `site/task-format.html`, `site/index.html`,
  `site/roadmap.html`, and `docs/ARCHITECTURE.md`.

What should be checked later
- Tool surface and result shapes. Confirm `data` payloads carry what the trace
  recorder (Milestone 5) and scorers (Milestone 8) will need — e.g. `run_tests`
  exposes `passed`; `git_diff` exposes per-file numstat and untracked files.
- `apply_patch` is a hand-rolled unified-diff applier. Worth a careful read: it
  applies exact-context only (no fuzz), is atomic across files, and handles
  create/modify/delete and the `\ No newline at end of file` marker. Edge cases
  to probe: CRLF files, files without a trailing newline patched in the middle,
  and patches with overlapping/mis-ordered hunks.
- `run_shell`/`run_tests` run with `shell=False`. Confirm this matches how tasks
  intend to express test commands (the task schema normalises a shell string to
  argv, so `python3 -m pytest -q` works, but a real pipeline would not).
- Workspace confinement (`ToolContext.resolve`) resolves symlinks before the
  containment check. Confirm this is the desired policy for `git_diff`'s untracked
  listing and for `search_repo`, which both walk the tree.
- `REGISTERED_TOOL_NAMES == tasks.KNOWN_TOOLS` is enforced by a test. Decide
  whether the schema should eventually import the registry's names directly
  rather than keeping a parallel constant guarded by a test.

Technical risks
- Medium-low. The tools execute real subprocesses (`run_shell`, `run_tests`,
  `git_diff`) and write files (`write_file`, `apply_patch`). Mitigations in place:
  no shell, output/time bounds, workspace confinement, and atomic patch
  application. There is **no** process isolation, resource cgroup, or network
  policy yet — that is Milestone 7. Do not run untrusted tasks against a real
  host workspace until the sandbox lands.
- `git_diff` requires a git repo; tests that need `git` are skipped when it is
  absent, so a `git`-less CI would silently cover less. The non-git path returns a
  structured failure rather than crashing.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime tools list`
- `PYTHONPATH=src python3 -m code_agent_runtime tools show apply_patch --json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
