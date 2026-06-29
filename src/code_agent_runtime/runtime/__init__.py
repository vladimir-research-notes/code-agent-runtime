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

Containment here is workspace confinement plus ``allowed_tools`` gating only; the
full sandbox (process/resource/network policy, secret scanning) is Milestone 7.
Tracing, full scoring, and suite reports are Milestones 5 and 8.
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
