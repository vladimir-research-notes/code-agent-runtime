"""The runtime state machine: drive an agent over a task (Milestone 4).

:func:`run_task` is the whole loop. Given a validated task and an agent, it walks
the stages the plan names — prepare workspace, run agent steps, execute tools,
run tests, score, report — and returns a single structured :class:`RunResult`.

Design choices:

- **The runtime owns side effects.** Agents only *propose*; the loop prepares the
  workspace, gates each call against ``allowed_tools``, dispatches it, runs the
  task's test command, and captures the final diff. This keeps a run reproducible
  regardless of which agent produced it.
- **Tests and diff are runtime-driven, not agent actions.** ``run_tests`` and
  ``git_diff`` are issued by the loop through the full registry, so they work
  even when the task does not grant those tools to the agent; they do not count
  toward the agent's ``tool_call_count`` / ``command_count``.
- **Minimal, honest scoring.** Milestone 4 scores ``test_command`` (pass iff the
  command exits zero) and ``none`` (not scored). The richer methods
  (``expected_files``, ``diff_constraint``, ``custom``) and the suite/regression
  machinery are Milestone 8; until then they resolve to ``not_scored`` with a
  note rather than a fabricated verdict.
- **No wall-clock timing.** Consistent with the tools layer; timing belongs to
  the trace recorder (Milestone 5).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..agents import Agent, Observation
from ..tasks import Task
from ..tools import ToolResult, build_registry
from .execution import (
    Workspace,
    WorkspaceError,
    dispatch_agent_call,
    make_context,
    prepare_workspace,
)
from .state import RunConfig, RunOutcome, RunPhase, RunResult, StepRecord

#: Tool names whose execution counts as "running a command" in the eval report.
_COMMAND_TOOLS = frozenset({"run_shell", "run_tests"})


def run_task(
    task: Task,
    agent: Agent,
    *,
    config: RunConfig | None = None,
    registry=None,
    workspace_dest=None,
) -> RunResult:
    """Run ``agent`` against ``task`` and return a structured :class:`RunResult`.

    The task is assumed already loaded and validated (the "load task" stage is the
    caller's, e.g. the CLI's ``run`` command). Workspace preparation failures are
    captured as an ``error`` outcome rather than raised, so a batch runner can
    keep going.
    """
    config = config or RunConfig()
    registry = registry or build_registry()
    allowed = frozenset(task.allowed_tools)

    steps: list[StepRecord] = []
    phase = RunPhase.PREPARING
    workspace: Workspace | None = None
    tests_data: Mapping[str, Any] | None = None
    diff_data: Mapping[str, Any] | None = None

    try:
        workspace = prepare_workspace(
            task, dest=workspace_dest, init_git=config.init_git
        )
        ctx = make_context(task, workspace, tool_timeout_seconds=config.tool_timeout_seconds)

        # --- agent loop ----------------------------------------------------
        phase = RunPhase.AGENT_LOOP
        agent.reset(task)
        last_result: ToolResult | None = None
        stop_reason = "agent finished"
        completed_loop = False
        for index in range(config.max_steps):
            action = agent.propose(Observation(task=task, step=index, last_result=last_result))
            if action.is_finish:
                stop_reason = action.message or "agent finished"
                steps.append(
                    StepRecord(
                        index=index,
                        action_kind="finish",
                        tool=None,
                        args={},
                        result=None,
                        allowed=True,
                        message=action.message,
                    )
                )
                completed_loop = True
                break
            call = action.call
            assert call is not None  # AgentAction invariant: non-finish ⇒ has a call
            result, was_allowed = dispatch_agent_call(registry, allowed, call, ctx)
            steps.append(
                StepRecord(
                    index=index,
                    action_kind="tool",
                    tool=call.tool,
                    args=dict(call.args),
                    result=result,
                    allowed=was_allowed,
                    message=action.message,
                )
            )
            last_result = result
        if not completed_loop:
            stop_reason = f"reached max_steps ({config.max_steps})"

        # --- run tests -----------------------------------------------------
        if config.run_tests and task.test_command is not None:
            phase = RunPhase.TESTING
            test_result = registry.get("run_tests").run(
                ctx,
                command=list(task.test_command),
                timeout_seconds=config.tool_timeout_seconds,
            )
            tests_data = test_result.data

        # --- capture final diff -------------------------------------------
        if workspace.git:
            phase = RunPhase.CAPTURING_DIFF
            diff_result = registry.get("git_diff").run(ctx)
            if diff_result.ok:
                diff_data = diff_result.data

        # --- score ---------------------------------------------------------
        phase = RunPhase.SCORING
        score = _score(task, tests_data)

        phase = RunPhase.REPORTING
        return _build_result(
            task=task,
            agent=agent,
            steps=steps,
            score=score,
            tests=tests_data,
            diff=diff_data,
            workspace=workspace,
            stop_reason=stop_reason,
            phase_reached=RunPhase.DONE,
            config=config,
        )
    except WorkspaceError as exc:
        return _error_result(task, agent, steps, str(exc), phase, workspace, config)
    except Exception as exc:  # pragma: no cover - defensive; surfaced, not swallowed
        return _error_result(task, agent, steps, repr(exc), phase, workspace, config)
    finally:
        if workspace is not None and not config.keep_workspace:
            workspace.cleanup()


def _score(task: Task, tests_data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Score the run per the task's ``scoring_method`` (Milestone 4 subset)."""
    method = task.scoring_method
    if method == "none":
        return {
            "method": method,
            "outcome": RunOutcome.NOT_SCORED,
            "passed": None,
            "detail": "task is not automatically scored (scoring_method 'none')",
        }
    if method == "test_command":
        if tests_data is None:
            return {
                "method": method,
                "outcome": RunOutcome.FAILED,
                "passed": False,
                "detail": "no test result (test command did not run)",
            }
        passed = bool(tests_data.get("passed"))
        return {
            "method": method,
            "outcome": RunOutcome.PASSED if passed else RunOutcome.FAILED,
            "passed": passed,
            "detail": "test command passed" if passed else "test command failed",
        }
    # expected_files / diff_constraint / custom are implemented in Milestone 8.
    return {
        "method": method,
        "outcome": RunOutcome.NOT_SCORED,
        "passed": None,
        "detail": f"scoring_method {method!r} is implemented in Milestone 8",
    }


def _counts(steps: list[StepRecord]) -> tuple[int, int]:
    """Return (tool_call_count, command_count) for the agent's steps.

    ``command_count`` counts executed exec-category tools (``run_shell`` /
    ``run_tests``); a blocked call did not run, so it is not a command.
    """
    tool_calls = sum(1 for s in steps if s.action_kind == "tool")
    commands = sum(1 for s in steps if s.tool in _COMMAND_TOOLS and s.allowed)
    return tool_calls, commands


def _build_result(
    *,
    task: Task,
    agent: Agent,
    steps: list[StepRecord],
    score: Mapping[str, Any],
    tests: Mapping[str, Any] | None,
    diff: Mapping[str, Any] | None,
    workspace: Workspace,
    stop_reason: str,
    phase_reached: str,
    config: RunConfig,
) -> RunResult:
    tool_calls, commands = _counts(steps)
    return RunResult(
        task_id=task.id,
        agent=agent.name,
        outcome=score["outcome"],
        phase_reached=phase_reached,
        stop_reason=stop_reason,
        steps=tuple(steps),
        tool_call_count=tool_calls,
        command_count=commands,
        score=dict(score),
        tests=tests,
        diff=diff,
        workspace=str(workspace.root),
        kept_workspace=config.keep_workspace,
        git=workspace.git,
    )


def _error_result(
    task: Task,
    agent: Agent,
    steps: list[StepRecord],
    error: str,
    phase: str,
    workspace: Workspace | None,
    config: RunConfig,
) -> RunResult:
    tool_calls, commands = _counts(steps)
    return RunResult(
        task_id=task.id,
        agent=agent.name,
        outcome=RunOutcome.ERROR,
        phase_reached=phase,
        stop_reason=f"run errored during {phase}",
        steps=tuple(steps),
        tool_call_count=tool_calls,
        command_count=commands,
        score={
            "method": task.scoring_method,
            "outcome": RunOutcome.ERROR,
            "passed": None,
            "detail": error,
        },
        tests=None,
        diff=None,
        workspace=str(workspace.root) if workspace is not None else None,
        kept_workspace=config.keep_workspace,
        git=workspace.git if workspace is not None else False,
        error=error,
    )
