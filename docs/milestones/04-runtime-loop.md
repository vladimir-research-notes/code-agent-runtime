# Milestone 4 — Local runtime state machine

## Summary

Implement the coding-agent runtime loop with deterministic agents. Given a
validated task and an agent, the runtime walks the stages the plan names —
**prepare workspace → run agent steps → execute tools → run tests → score →
report** — and returns one structured `RunResult`. The runtime owns every side
effect; agents only *propose* actions. Two model-free baselines ship: a `mock`
null agent and a `scripted` replay agent with built-in solutions for the example
tasks. This is the first milestone where a task is actually *run*, not just
described.

## Deliverables

- `src/code_agent_runtime/agents/` package:
  - `base.py` — `Agent`, `AgentAction` (`tool`/`finish`), `Observation`.
  - `mock_agent.py` — `MockAgent`, the null baseline (no actions, finishes).
  - `scripted_agent.py` — `ScriptedAgent`, replays a fixed plan then finishes.
  - `solutions.py` — built-in scripted solutions for the shipped tasks
    (`build_scripted_agent`, `has_solution`, `SOLUTIONS`).
- `src/code_agent_runtime/runtime/` package:
  - `state.py` — `RunPhase`, `RunOutcome`, `RunConfig`, `StepRecord`, `RunResult`.
  - `execution.py` — `prepare_workspace`/`Workspace`, git init, `make_context`,
    `dispatch_agent_call` (allowed-tool gating).
  - `agent_loop.py` — `run_task`, the state machine; minimal `_score`.
  - `report.py` — `format_run_report`, a concise per-run text summary.
  - `__init__.py` — public API re-exports.
- CLI: `run <task> [--agent mock|scripted] [--max-steps N] [--no-tests]
  [--keep-workspace] [--json]`; `info` now reports Milestone 4.
- `tests/test_runtime.py` (unit + integration); `tests/test_scaffold_layout.py`
  extended for the Milestone 4 notes.

## The loop, stage by stage

| Stage | What happens | Owner |
| --- | --- | --- |
| load task | validate the task, resolve the fixture | caller / CLI |
| prepare workspace | copy fixture to a fresh temp dir; `git init` + commit | runtime |
| agent step | `agent.propose(Observation)` → `AgentAction` | agent |
| execute tool | gate against `allowed_tools`, then dispatch via registry | runtime |
| run tests | run the task's `test_command` via the `run_tests` tool | runtime |
| score | `test_command` → pass/fail; `none` → not scored | runtime |
| report | build `RunResult`; `format_run_report` / JSON | runtime |

## Design notes / decisions

- **Agents propose; the runtime acts.** The agent contract is two methods
  (`reset`, `propose`) over a tiny `Observation`. All side effects — workspace
  prep, gating, dispatch, tests, diff capture — live in the runtime, so a run is
  reproducible regardless of the agent. The same interface will carry the
  optional LLM adapters (Milestone 10) without changing the loop.
- **Workspace is a disposable copy.** `prepare_workspace` copies the fixture
  (minus caches/vcs) into a temp dir, so a run never mutates the committed
  fixture, and `git init`s it so the final diff can be captured. The workspace is
  removed after the run unless `--keep-workspace`. Git absence degrades
  gracefully (`git=False`, diff omitted) rather than failing the run.
- **Tests and diff are runtime-driven.** `run_tests` and `git_diff` are issued by
  the loop through the full registry, so they work even when the task does not
  grant those tools to the agent, and they do **not** count toward the agent's
  `tool_call_count` / `command_count`.
- **`allowed_tools` gating is a capability check, not the sandbox.** A call to a
  tool the task did not grant is blocked (category `blocked`, recorded, not
  executed). Path confinement is inherited from the tools (Milestone 3);
  process/resource/network policy and secret scanning remain Milestone 7.
- **Minimal, honest scoring.** Only `test_command` and `none` are scored here;
  `expected_files` / `diff_constraint` / `custom` resolve to `not_scored` with a
  note pointing at Milestone 8 rather than a fabricated verdict. The full scorer,
  suite runner, and reports are Milestone 8.
- **No wall-clock timing.** Consistent with the tools layer; timing is the trace
  recorder's job (Milestone 5), which keeps `RunResult` deterministic and
  unit-testable.
- **Deviation from the planned file split.** The plan sketched
  `runtime/context.py` and `runtime/tool_registry.py`; these are collapsed —
  per-run context is `RunConfig` + the existing `ToolContext`, and the tool
  registry already lives in `tools/`. Recorded honestly here.

## Validation

- `python3 -m pytest -q` — all tests pass (adds `tests/test_runtime.py`: agent
  interface, workspace prep, gating, scoring, and end-to-end runs). The
  acceptance test `test_scripted_agent_completes_bugfix` drives the scripted
  agent from failing tests to passing on `bugfix/sum-range-off-by-one`;
  `test_scripted_run_captures_final_diff` asserts the diff is captured (skips
  without `git`); `test_mock_agent_leaves_bugfix_failing` confirms the null
  baseline.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one`
  — scripted agent; outcome `passed`.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent mock`
  — null baseline; outcome `failed`.
- `python3 scripts/04_check_repo_hygiene.py` — repo stays clean.

## Status

Complete. Next: Milestone 5 — Trace recorder.
