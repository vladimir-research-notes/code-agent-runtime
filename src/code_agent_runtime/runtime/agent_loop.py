"""The runtime state machine: drive an agent over a task (Milestone 4).

:func:`run_task` is the whole loop. Given a validated task and an agent, it walks
the stages the plan names — prepare workspace, run agent steps, execute tools,
run tests, score, report — and returns a single structured :class:`RunResult`.

Design choices:

- **The runtime owns side effects.** Agents only *propose*; the loop prepares the
  workspace, gates each call against ``allowed_tools`` and the sandbox policy
  (Milestone 7), dispatches it, runs the task's test command, and captures the
  final diff. This keeps a run reproducible regardless of which agent produced it.
- **Tests and diff are runtime-driven, not agent actions.** ``run_tests`` and
  ``git_diff`` are issued by the loop through the full registry, so they work
  even when the task does not grant those tools to the agent; they do not count
  toward the agent's ``tool_call_count`` / ``command_count``.
- **Scoring is delegated.** The loop hands the evidence it gathered — the test
  result, the captured diff, and the live workspace — to
  :func:`code_agent_runtime.scoring.score_run`, which dispatches on the task's
  ``scoring_method`` (``test_command``, ``expected_files``, ``diff_constraint``,
  ``custom``, ``none``) and returns a verdict (Milestone 8). The run is scored
  *before* the workspace is cleaned up so a filesystem-checking scorer can read
  it. The suite runner and reports live in :mod:`code_agent_runtime.scoring` and
  :mod:`code_agent_runtime.reports`.
- **No wall-clock timing in the result.** Consistent with the tools layer, the
  :class:`RunResult` stays deterministic and timing-free. Timing lives in the
  optional trace recorder (Milestone 5): pass ``recorder=`` and the loop emits a
  timestamped event at each stage. The loop never imports the tracer — it calls a
  duck-typed object and skips it when ``recorder is None`` — so an untraced run is
  unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..agents import Agent, Observation
from ..sandbox import Sandbox, SandboxPolicy
from ..scoring import score_run
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
    recorder=None,
    policy: SandboxPolicy | None = None,
) -> RunResult:
    """Run ``agent`` against ``task`` and return a structured :class:`RunResult`.

    The task is assumed already loaded and validated (the "load task" stage is the
    caller's, e.g. the CLI's ``run`` command). Workspace preparation failures are
    captured as an ``error`` outcome rather than raised, so a batch runner can
    keep going.

    ``recorder`` is an optional :class:`~code_agent_runtime.traces.TraceRecorder`
    (or any object with the same lifecycle methods). When given, the loop emits a
    timestamped event at each stage and ``recorder.finish(result)`` is called
    before returning, so ``recorder.trace`` holds the complete trace. When
    ``None``, tracing is skipped entirely and the run is byte-for-byte unchanged.

    ``policy`` is the Milestone 7 :class:`~code_agent_runtime.sandbox.SandboxPolicy`
    enforced on every *agent* tool call (path/command/network gating plus output
    redaction). It defaults to :meth:`SandboxPolicy.from_task`. Enforcement is
    governed by ``config.enforce_sandbox`` (on by default); when off, the run uses
    pure ``allowed_tools`` gating and no redaction. The runtime-driven test and
    diff commands are issued by the loop itself, not by the agent, so they are not
    policy-gated — but their captured output **is** redacted when a policy is
    active, so a secret a test surfaces never lands unredacted in the trace.
    """
    config = config or RunConfig()
    registry = registry or build_registry()
    allowed = frozenset(task.allowed_tools)
    effective_policy = policy or SandboxPolicy.from_task(task)
    sandbox = Sandbox(effective_policy) if config.enforce_sandbox else None
    policy_dict = effective_policy.to_dict() if sandbox is not None else None

    steps: list[StepRecord] = []
    phase = RunPhase.PREPARING
    workspace: Workspace | None = None
    tests_data: Mapping[str, Any] | None = None
    diff_data: Mapping[str, Any] | None = None

    if recorder is not None:
        recorder.start(task=task, agent=agent.name, config=config)

    try:
        workspace = prepare_workspace(
            task, dest=workspace_dest, init_git=config.init_git
        )
        if recorder is not None:
            recorder.workspace_prepared(workspace)
        ctx = make_context(
            task,
            workspace,
            tool_timeout_seconds=config.tool_timeout_seconds,
            policy=effective_policy if sandbox is not None else None,
        )

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
                if recorder is not None:
                    recorder.agent_step(steps[-1])
                completed_loop = True
                break
            call = action.call
            assert call is not None  # AgentAction invariant: non-finish ⇒ has a call
            result, was_allowed = dispatch_agent_call(
                registry, allowed, call, ctx, sandbox=sandbox
            )
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
            if recorder is not None:
                recorder.agent_step(steps[-1])
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
            # The test command is runtime-issued (not policy-gated), but its
            # captured output is still scrubbed so a secret it prints never lands
            # unredacted in the trace.
            if sandbox is not None:
                test_result = sandbox.redact_result(test_result)
            tests_data = test_result.data
            if recorder is not None:
                recorder.tests_ran(test_result)

        # --- capture final diff -------------------------------------------
        if workspace.git:
            phase = RunPhase.CAPTURING_DIFF
            diff_result = registry.get("git_diff").run(ctx)
            if sandbox is not None:
                diff_result = sandbox.redact_result(diff_result)
            if diff_result.ok:
                diff_data = diff_result.data
                if recorder is not None:
                    recorder.diff_captured(diff_result)

        # --- score ---------------------------------------------------------
        # Scored before the workspace is cleaned up (the `finally` below), so the
        # filesystem-checking scorer (`expected_files`) can read it.
        phase = RunPhase.SCORING
        score = _score(task, tests_data, diff=diff_data, workspace=workspace.root)
        if recorder is not None:
            recorder.scored(score)

        phase = RunPhase.REPORTING
        result = _build_result(
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
            policy=policy_dict,
        )
        return _finish_trace(recorder, result)
    except WorkspaceError as exc:
        result = _error_result(task, agent, steps, str(exc), phase, workspace, config, policy_dict)
        return _finish_trace(recorder, result)
    except Exception as exc:  # pragma: no cover - defensive; surfaced, not swallowed
        result = _error_result(task, agent, steps, repr(exc), phase, workspace, config, policy_dict)
        return _finish_trace(recorder, result)
    finally:
        if workspace is not None and not config.keep_workspace:
            workspace.cleanup()


def _finish_trace(recorder, result: RunResult) -> RunResult:
    """Close the trace (if recording) and return ``result`` unchanged."""
    if recorder is not None:
        recorder.finish(result)
    return result


def _score(
    task: Task,
    tests_data: Mapping[str, Any] | None,
    *,
    diff: Mapping[str, Any] | None = None,
    workspace: Any = None,
) -> dict[str, Any]:
    """Score the run via the :mod:`code_agent_runtime.scoring` layer (Milestone 8).

    Delegates to :func:`scoring.score_run`, which dispatches on the task's
    ``scoring_method`` (``test_command``, ``expected_files``, ``diff_constraint``,
    ``custom``, ``none``). Returns the verdict as the plain dict the loop stores as
    ``RunResult.score`` — the same four-key shape as before, now with optional
    per-check ``checks`` / ``extra`` keys. ``workspace`` is the live workspace path
    so the ``expected_files`` scorer can inspect it; ``diff`` is the captured diff
    the ``diff_constraint`` scorer constrains.
    """
    return score_run(task, tests=tests_data, diff=diff, workspace=workspace).to_dict()


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
    policy: Mapping[str, Any] | None = None,
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
        policy=policy,
    )


def _error_result(
    task: Task,
    agent: Agent,
    steps: list[StepRecord],
    error: str,
    phase: str,
    workspace: Workspace | None,
    config: RunConfig,
    policy: Mapping[str, Any] | None = None,
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
        policy=policy,
    )
