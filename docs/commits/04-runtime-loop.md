# Commit note — Milestone 4

**Commit message:** `Add local agent runtime state machine`

## What this commit adds

- `src/code_agent_runtime/agents/` — the agent layer:
  - `base.py`: `Agent`, `AgentAction`, `Observation`.
  - `mock_agent.py`: `MockAgent` (null baseline).
  - `scripted_agent.py`: `ScriptedAgent` (deterministic replay).
  - `solutions.py`: built-in scripted solutions for the shipped tasks
    (`build_scripted_agent`, `has_solution`).
- `src/code_agent_runtime/runtime/` — the runtime state machine:
  - `state.py`: `RunPhase`, `RunOutcome`, `RunConfig`, `StepRecord`, `RunResult`.
  - `execution.py`: workspace preparation/copy + `git init`, `make_context`,
    `dispatch_agent_call` (allowed-tool gating).
  - `agent_loop.py`: `run_task` (load → prepare → loop → test → score → report)
    and a minimal scorer.
  - `report.py`: `format_run_report`.
- CLI: `run` subcommand (mock/scripted, `--max-steps`, `--no-tests`,
  `--keep-workspace`, `--json`); `info` now reports Milestone 4.
- Tests: `tests/test_runtime.py` (unit + integration over the shipped fixtures);
  `tests/test_scaffold_layout.py` extended for the Milestone 4 notes.
- Docs/site: `site/index.html`, `site/architecture.html`, `site/roadmap.html`,
  `site/evals.html`, `site/tracing-replay.html` updated; `docs/ARCHITECTURE.md`
  and `README.md` status updated.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (the patch in the scripted solution is built with the
stdlib `difflib`; git is the already-required binary). Workspaces are disposable
temp copies removed after each run unless `--keep-workspace`. Containment is
workspace confinement + `allowed_tools` gating only — **not** process/resource/
network isolation, which is Milestone 7. No paid API is used or required.

## Verification at commit time

- `python3 -m pytest -q` passes (git/pytest-dependent runtime tests skip if `git`
  is unavailable).
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one`
  reports outcome `passed`; `--agent mock` reports `failed`.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
