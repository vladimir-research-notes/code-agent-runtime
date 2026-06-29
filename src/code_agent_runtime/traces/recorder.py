"""The trace recorder and its clock (Milestone 5).

:class:`TraceRecorder` is the stateful object that turns a run into a
:class:`Trace`. The runtime loop (:func:`code_agent_runtime.runtime.run_task`)
drives it through a small, explicit lifecycle — :meth:`start`,
:meth:`workspace_prepared`, :meth:`agent_step`, :meth:`tests_ran`,
:meth:`diff_captured`, :meth:`scored`, :meth:`finish` — calling each method at
the matching stage. The recorder owns the *when* (timestamps) and the
phase-to-event mapping; the loop only says *what* happened. The loop never
imports this module: it calls these methods on a duck-typed object and skips
them when no recorder is supplied, so tracing is strictly opt-in and adds nothing
to an untraced run.

Time is taken through an injectable :class:`Clock` so traces are testable.
Production uses the real :func:`time.time` (wall clock, for human-readable
timestamps) and :func:`time.monotonic` (for durations); tests inject a
deterministic fake. Wall-clock and monotonic time are kept separate on purpose:
the monotonic clock is the correct source for ``elapsed``/``duration`` because it
cannot jump when the system clock is adjusted.
"""

from __future__ import annotations

import datetime as _dt
import time
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from ..runtime.execution import Workspace
from ..runtime.state import RunConfig, RunPhase, RunResult, StepRecord
from ..tasks import Task
from ..tools import ToolResult
from .schema import SCHEMA_VERSION, TRACE_EVENT_KINDS, Trace, TraceEvent


class Clock:
    """Source of wall-clock and monotonic time, injectable for tests.

    The default reads the real clocks. A test supplies a subclass (or any object
    with the same two methods) to make a trace fully deterministic.
    """

    def wall(self) -> float:
        """Wall-clock time as epoch seconds (UTC)."""
        return time.time()

    def monotonic(self) -> float:
        """Monotonic time in seconds; only differences are meaningful."""
        return time.monotonic()


def default_trace_id(task_id: str, started_wall: float) -> str:
    """Build a readable, mostly-unique trace id from a task id and start time.

    Sub-second precision is included so two runs of the same task in the same
    second do not collide; uniqueness is best-effort, not guaranteed (a caller
    that needs a hard guarantee should pass an explicit ``trace_id``).
    """
    slug = task_id.replace("/", "_")
    return f"{slug}-{started_wall:.3f}"


class TraceRecorder:
    """Builds a :class:`Trace` from a run, one lifecycle call at a time."""

    def __init__(self, *, clock: Clock | None = None, trace_id: str | None = None) -> None:
        self._clock = clock or Clock()
        self._explicit_id = trace_id
        self._events: list[TraceEvent] = []
        self._seq = 0
        # Set in start(); a recorder must be started before any event.
        self._started = False
        self._started_wall = 0.0
        self._started_mono = 0.0
        self._trace_id = ""
        self._task: Mapping[str, Any] = {}
        self._agent = ""
        self._config: Mapping[str, Any] = {}
        self._workspace: Mapping[str, Any] | None = None
        self._trace: Trace | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self, *, task: Task, agent: str, config: RunConfig) -> None:
        """Begin a trace: pin the start time and record run metadata."""
        self._started = True
        self._started_wall = self._clock.wall()
        self._started_mono = self._clock.monotonic()
        self._task = _task_metadata(task)
        self._agent = agent
        self._config = asdict(config)
        self._trace_id = self._explicit_id or default_trace_id(task.id, self._started_wall)
        self._emit(
            "run_started",
            RunPhase.PREPARING,
            f"run started: {task.id} (agent: {agent})",
            {"task_id": task.id, "agent": agent, "config": self._config},
        )

    def workspace_prepared(self, workspace: Workspace) -> None:
        meta = {
            "root": str(workspace.root),
            "fixture": str(workspace.fixture),
            "git": workspace.git,
        }
        self._workspace = meta
        self._emit(
            "workspace_prepared",
            RunPhase.PREPARING,
            f"workspace prepared (git: {'yes' if workspace.git else 'no'})",
            meta,
        )

    def agent_step(self, step: StepRecord) -> None:
        """Record one agent step (a tool call or the finish action)."""
        if step.action_kind == "finish":
            self._emit(
                "agent_finish",
                RunPhase.AGENT_LOOP,
                f"agent finished: {step.message or 'done'}",
                {"index": step.index, "message": step.message},
            )
            return
        result = step.result
        data: dict[str, Any] = {
            "index": step.index,
            "tool": step.tool,
            "args": dict(step.args),
            "allowed": step.allowed,
            "ok": bool(result.ok) if result is not None else None,
            "category": result.category if result is not None else None,
        }
        if result is not None:
            # Surface the exit status for exec-category tools; full stdout/stderr
            # stays in result.steps (embedded under Trace.result), not here.
            if "exit_code" in result.data:
                data["exit_code"] = result.data.get("exit_code")
            if not result.ok and result.error:
                data["error"] = result.error
        summary = result.summary if result is not None else f"{step.tool} (no result)"
        self._emit("tool_call", RunPhase.AGENT_LOOP, summary, data)

    def tests_ran(self, result: ToolResult) -> None:
        d = result.data
        self._emit(
            "tests_ran",
            RunPhase.TESTING,
            result.summary,
            {
                "passed": d.get("passed"),
                "exit_code": d.get("exit_code"),
                "timed_out": d.get("timed_out"),
                "truncated": d.get("truncated"),
            },
        )

    def diff_captured(self, result: ToolResult) -> None:
        d = result.data
        self._emit(
            "diff_captured",
            RunPhase.CAPTURING_DIFF,
            result.summary,
            {
                "files": len(d.get("files", [])),
                "insertions": d.get("insertions"),
                "deletions": d.get("deletions"),
                "untracked": len(d.get("untracked", [])),
                "truncated": d.get("truncated"),
            },
        )

    def scored(self, score: Mapping[str, Any]) -> None:
        self._emit(
            "scored",
            RunPhase.SCORING,
            str(score.get("detail", "")),
            {
                "method": score.get("method"),
                "outcome": score.get("outcome"),
                "passed": score.get("passed"),
            },
        )

    def finish(self, result: RunResult) -> Trace:
        """Close the trace with the run's result and return the built Trace.

        Idempotent guard aside, this is the terminal call: it emits
        ``run_finished``, stamps the finish time and duration, and assembles the
        immutable :class:`Trace`, also available afterwards as :attr:`trace`.
        """
        self._emit(
            "run_finished",
            result.phase_reached,
            f"run finished: {result.outcome}",
            {
                "outcome": result.outcome,
                "phase_reached": result.phase_reached,
                "stop_reason": result.stop_reason,
                "error": result.error,
            },
        )
        finished_wall = self._clock.wall()
        duration = self._clock.monotonic() - self._started_mono
        self._trace = Trace(
            schema_version=SCHEMA_VERSION,
            trace_id=self._trace_id,
            task=self._task,
            agent=self._agent,
            config=self._config,
            workspace=self._workspace,
            started_at=self._started_wall,
            started_at_iso=_iso_utc(self._started_wall),
            finished_at=finished_wall,
            duration_seconds=duration,
            outcome=result.outcome,
            events=tuple(self._events),
            result=result.to_dict(),
        )
        return self._trace

    # -- accessors ----------------------------------------------------------

    @property
    def trace(self) -> Trace | None:
        """The built :class:`Trace`, or ``None`` until :meth:`finish` is called."""
        return self._trace

    # -- internals ----------------------------------------------------------

    def _emit(self, kind: str, phase: str, summary: str, data: Mapping[str, Any]) -> None:
        if not self._started:  # pragma: no cover - programmer error guard
            raise RuntimeError("TraceRecorder.start() must be called before recording events")
        if kind not in TRACE_EVENT_KINDS:  # pragma: no cover - guards a typo above
            raise ValueError(f"unknown trace event kind {kind!r}")
        self._events.append(
            TraceEvent(
                seq=self._seq,
                kind=kind,
                phase=phase,
                timestamp=self._clock.wall(),
                elapsed_seconds=self._clock.monotonic() - self._started_mono,
                summary=summary,
                data=dict(data),
            )
        )
        self._seq += 1


def _task_metadata(task: Task) -> dict[str, Any]:
    """The task-metadata block embedded at the top of a trace."""
    return {
        "id": task.id,
        "title": task.title,
        "version": task.version,
        "prompt": task.prompt,
        "scoring_method": task.scoring_method,
        "test_command": list(task.test_command) if task.test_command is not None else None,
        "allowed_tools": list(task.allowed_tools),
        "fixture": task.fixture,
        "timeout_seconds": task.timeout_seconds,
        "resource_limits": task.resource_limits.to_dict(),
        "metadata": dict(task.metadata),
        "source_path": task.source_path,
    }


def _iso_utc(epoch: float) -> str:
    """Render epoch seconds as an ISO-8601 UTC string (human-readable timestamp)."""
    return _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc).isoformat()
