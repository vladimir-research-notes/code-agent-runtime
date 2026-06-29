Human review: Milestone 4 — Local runtime state machine

TL;DR
Adds the runtime loop that turns a task + agent into a scored, structured
`RunResult`. The runtime prepares a disposable workspace (fixture copy + `git
init`), drives the agent step by step, gates each tool call against the task's
`allowed_tools`, runs the task's test command, captures the final diff, scores,
and reports. Two deterministic, model-free agents ship: `MockAgent` (null
baseline) and `ScriptedAgent` (replay), with built-in solutions for the example
tasks. The acceptance test drives the scripted agent from failing tests to
passing on `bugfix/sum-range-off-by-one`; the mock agent leaves it failing.
Covered by `tests/test_runtime.py`.

What changed
- Added `src/code_agent_runtime/agents/` (`base`, `mock_agent`, `scripted_agent`,
  `solutions`, `__init__`).
- Added `src/code_agent_runtime/runtime/` (`state`, `execution`, `agent_loop`,
  `report`, `__init__`).
- Added CLI `run`; `info` now reports Milestone 4.
- Added `tests/test_runtime.py`; extended `tests/test_scaffold_layout.py`.
- Updated `site/index.html`, `site/architecture.html`, `site/roadmap.html`,
  `site/evals.html`, `site/tracing-replay.html`, `docs/ARCHITECTURE.md`, `README.md`.

What should be checked later
- `RunResult` shape. Confirm it carries what the trace recorder (Milestone 5) and
  the eval report (Milestone 8) need: per-step records (action, args, result,
  allowed), `tool_call_count` / `command_count`, `tests`, `diff`, `score`,
  `outcome`, `phase_reached`, `stop_reason`. Note there is **no timing** yet (by
  design — timing belongs to the tracer).
- Scripted solutions. `solutions.py` builds the bugfix patch from the live
  fixture via `difflib` (so context matches the workspace copy) and rewrites
  `greet.py` whole for the CLI task. Worth confirming this is the desired
  solver/agent boundary: the `ScriptedAgent` is observation-blind; all
  task-specific reasoning is precomputed in the builder. Decide whether future,
  smarter scripted solutions should be allowed to react to observations.
- Workspace lifecycle. Workspaces are `tempfile.mkdtemp` copies removed in a
  `finally` unless `--keep-workspace`. Confirm temp-dir placement and cleanup
  policy suit your environment; the recorded `workspace` path will not exist after
  a normal run (intentional until replay/M6 needs it).
- Git dependency. The final diff is captured only when `git` is present and
  `git init` succeeds; otherwise `git=False` and `diff=None`. Tests needing `git`
  skip when it is absent, so a `git`-less CI covers less.
- Scoring scope. Only `test_command` and `none` are scored; other methods return
  `not_scored`. Confirm this is acceptable until Milestone 8 implements the full
  scorer and suite runner.

Technical risks
- Medium. The runtime executes real subprocesses (the task's test command via
  `run_tests`, plus `git`) and writes files into a workspace copy. Mitigations:
  the workspace is a disposable copy (the committed fixture is never mutated),
  tools are confined to the workspace, output/time are bounded, and tool calls
  are gated by `allowed_tools`. There is still **no** process isolation, resource
  cgroup, or network policy — that is Milestone 7. Do not run untrusted tasks
  against a real host until the sandbox lands.
- The loop catches a broad `Exception` around the run body to convert unexpected
  failures into an `error` outcome (so a batch runner survives one bad task).
  Confirm this does not mask programmer errors you would rather see raised; it is
  scoped to the run body, and tool-level anticipated failures are already
  structured results, not exceptions.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent mock`
- `PYTHONPATH=src python3 -m code_agent_runtime run cli/add-shout-flag --json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
