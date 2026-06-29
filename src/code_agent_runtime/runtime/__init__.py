"""The local agent runtime state machine (Milestone 4).

Turns a validated task and an agent into a structured, scored :class:`RunResult`
by walking the stages the plan names — prepare workspace, run agent steps,
execute tools, run tests, score, report — with the runtime owning every side
effect and gating each agent tool call against the task's ``allowed_tools``.

Public API:

- :func:`run_task` — drive an agent over a task; the one entry point.
- :class:`RunConfig`, :class:`RunResult`, :class:`StepRecord`, :class:`RunPhase`,
  :class:`RunOutcome` — configuration and the run record vocabulary.
- :func:`prepare_workspace`, :class:`Workspace`, :class:`WorkspaceError` — the
  workspace primitives.
- :func:`format_run_report` — a concise text summary of a run.

Containment is workspace confinement, ``allowed_tools`` capability gating, and the
Milestone 7 sandbox policy (allowed/denied paths, command allow/deny, network
flag, runtime/output caps, and secret redaction) — enforced on every agent tool
call when ``RunConfig.enforce_sandbox`` is on (the default); see
:mod:`code_agent_runtime.sandbox`. There is no process/namespace isolation (a
containerised runner is a documented non-goal for now). Full scoring and suite
reports are Milestone 8. Structured tracing (Milestone 5) is opt-in: pass
``recorder=`` to :func:`run_task` (see :mod:`code_agent_runtime.traces`); an
untraced run is unchanged.
"""

from __future__ import annotations

from .agent_loop import run_task
from .execution import Workspace, WorkspaceError, prepare_workspace
from .report import format_run_report
from .state import RunConfig, RunOutcome, RunPhase, RunResult, StepRecord

__all__ = [
    "run_task",
    "RunConfig",
    "RunResult",
    "StepRecord",
    "RunPhase",
    "RunOutcome",
    "prepare_workspace",
    "Workspace",
    "WorkspaceError",
    "format_run_report",
]
