"""Replay: reconstruct a run from its trace, without re-executing (Milestone 6).

A trace (:mod:`.schema`) is the complete record of one run; this module turns
that record back into a structured, inspectable view of what happened. *Replay*
here means **reconstruction, not re-execution**: it reads a stored
:class:`~code_agent_runtime.traces.schema.Trace` and rebuilds the things a person
debugging the run wants — the action timeline, the tool calls, the diff, the
tests, and the **failure point** — without preparing a workspace, dispatching a
tool, or running a command. (Re-executing a trace step by step to confirm it
reproduces is a later, optional capability; the plan only asks Milestone 6 to
reconstruct.)

The value this adds over the raw trace is *interpretation*. A bare pass/fail
verdict hides useful failure modes that are visible in the timeline — a tool the
permission gate blocked, a tool that returned an error, a test command that
failed, a run that errored before it finished. Replay surfaces these as
:class:`Anomaly` records and picks the one that best explains the verdict as the
:class:`ReplayedRun.failure_point`. This is the concrete handle on the project's
research question *"how often do final scores hide failure modes visible in
traces?"* — an `Anomaly` on a run that still passed is exactly such a case.

Everything here is pure: it consumes a :class:`Trace` and returns immutable data.
Rendering a :class:`ReplayedRun` as text or Markdown is :mod:`.summarize`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..runtime.state import RunOutcome, RunPhase
from .schema import Trace, TraceEvent

#: Tool names whose execution counts as "running a command", mirroring the
#: runtime's own definition (``runtime.agent_loop._COMMAND_TOOLS``). Kept here so
#: replay can derive ``command_count`` from the timeline alone, without importing
#: a private runtime constant.
_COMMAND_TOOLS: frozenset[str] = frozenset({"run_shell", "run_tests"})

#: Closed vocabulary of anomaly kinds, in the rough order they occur in a run.
#: ``blocked_tool`` — a tool call the permission gate refused; ``tool_error`` — a
#: tool that ran but returned ``ok=False``; ``tests_failed`` — the task's test
#: command exited non-zero; ``run_error`` — the run errored before finishing
#: (e.g. workspace preparation failed).
ANOMALY_KINDS: frozenset[str] = frozenset(
    {"blocked_tool", "tool_error", "tests_failed", "run_error"}
)


@dataclass(frozen=True)
class ToolCallView:
    """One reconstructed tool call from the timeline.

    Built from a ``tool_call`` event's compact payload (the full stdout/stderr
    lives once in ``Trace.result``, not here). ``step_index`` is the agent-loop
    step index; ``seq`` is the trace-event sequence number. ``ok`` is ``None`` for
    a call with no recorded result, ``False`` for a failure (including a blocked
    call's synthesised failure), ``True`` for success.
    """

    step_index: int | None
    seq: int
    elapsed_seconds: float
    tool: str
    args: Mapping[str, Any]
    allowed: bool
    ok: bool | None
    category: str | None
    exit_code: int | None
    summary: str
    error: str | None

    @property
    def blocked(self) -> bool:
        """The permission gate refused this call (it did not run)."""
        return not self.allowed

    @property
    def failed(self) -> bool:
        """The call ran but returned an error (distinct from being blocked)."""
        return self.allowed and self.ok is False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "seq": self.seq,
            "elapsed_seconds": self.elapsed_seconds,
            "tool": self.tool,
            "args": dict(self.args),
            "allowed": self.allowed,
            "ok": self.ok,
            "category": self.category,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "error": self.error,
            "blocked": self.blocked,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class Anomaly:
    """One thing that went wrong in a run, reconstructed from the trace.

    Anomalies are what a bare pass/fail verdict can hide: a blocked or failed
    tool call, a failing test command, or a run that errored out. ``kind`` is a
    member of :data:`ANOMALY_KINDS`; ``seq``/``phase``/``elapsed_seconds`` locate
    the anomaly on the timeline; ``detail`` is a short, specific cause.
    """

    kind: str
    seq: int
    phase: str
    elapsed_seconds: float
    summary: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "seq": self.seq,
            "phase": self.phase,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ReplayedRun:
    """A run reconstructed from its trace, without re-executing anything.

    Holds the interpreted view the debugging tooling renders: the ordered
    ``timeline`` (the trace's events), the ``tool_calls`` extracted from it, the
    ``tests`` and ``diff`` payloads, every ``anomaly`` detected, and the single
    ``failure_point`` that best explains the verdict (``None`` for a run that
    passed or was not scored). The counts mirror the runtime's own accounting so a
    replay can be cross-checked against the original :class:`RunResult`.
    """

    trace_id: str
    schema_version: int
    task_id: str
    task_title: str
    agent: str
    outcome: str | None
    started_at_iso: str
    duration_seconds: float | None
    timeline: tuple[TraceEvent, ...]
    tool_calls: tuple[ToolCallView, ...]
    tests: Mapping[str, Any] | None
    diff: Mapping[str, Any] | None
    anomalies: tuple[Anomaly, ...]
    failure_point: Anomaly | None
    tool_call_count: int
    blocked_count: int
    failed_tool_count: int
    command_count: int

    @property
    def passed(self) -> bool:
        return self.outcome == RunOutcome.PASSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "agent": self.agent,
            "outcome": self.outcome,
            "started_at_iso": self.started_at_iso,
            "duration_seconds": self.duration_seconds,
            "timeline": [e.to_dict() for e in self.timeline],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "tests": dict(self.tests) if self.tests is not None else None,
            "diff": dict(self.diff) if self.diff is not None else None,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "failure_point": self.failure_point.to_dict()
            if self.failure_point is not None
            else None,
            "counts": {
                "tool_calls": self.tool_call_count,
                "blocked": self.blocked_count,
                "failed_tools": self.failed_tool_count,
                "commands": self.command_count,
            },
        }


def replay_trace(trace: Trace) -> ReplayedRun:
    """Reconstruct a :class:`ReplayedRun` from ``trace`` without re-executing.

    Single pass over the events to extract the tool calls and detect anomalies as
    they occur, then resolve the ``tests`` / ``diff`` payloads (preferring the
    full embedded ``result``, falling back to the corresponding event) and pick
    the ``failure_point``.
    """
    result: Mapping[str, Any] = trace.result or {}

    tool_calls: list[ToolCallView] = []
    anomalies: list[Anomaly] = []
    tests_event: TraceEvent | None = None
    diff_event: TraceEvent | None = None
    finished_event: TraceEvent | None = None

    for ev in trace.events:
        if ev.kind == "tool_call":
            view = _tool_call_view(ev)
            tool_calls.append(view)
            if view.blocked:
                anomalies.append(
                    Anomaly(
                        kind="blocked_tool",
                        seq=ev.seq,
                        phase=ev.phase,
                        elapsed_seconds=ev.elapsed_seconds,
                        summary=f"blocked tool call: {view.tool}",
                        detail=view.error or ev.summary,
                    )
                )
            elif view.failed:
                anomalies.append(
                    Anomaly(
                        kind="tool_error",
                        seq=ev.seq,
                        phase=ev.phase,
                        elapsed_seconds=ev.elapsed_seconds,
                        summary=f"tool error: {view.tool}",
                        detail=view.error or ev.summary,
                    )
                )
        elif ev.kind == "tests_ran":
            tests_event = ev
        elif ev.kind == "diff_captured":
            diff_event = ev
        elif ev.kind == "run_finished":
            finished_event = ev

    tests = _resolve_tests(result, tests_event)
    diff = _resolve_diff(result, diff_event)

    if tests is not None and tests.get("passed") is False:
        loc = tests_event or finished_event
        anomalies.append(
            Anomaly(
                kind="tests_failed",
                seq=loc.seq if loc is not None else -1,
                phase=loc.phase if loc is not None else RunPhase.TESTING,
                elapsed_seconds=loc.elapsed_seconds if loc is not None else 0.0,
                summary="test command failed",
                detail=_tests_detail(tests),
            )
        )

    if trace.outcome == RunOutcome.ERROR:
        anomalies.append(
            Anomaly(
                kind="run_error",
                seq=finished_event.seq if finished_event is not None else -1,
                phase=str(result.get("phase_reached") or RunPhase.ERROR),
                elapsed_seconds=(
                    finished_event.elapsed_seconds if finished_event is not None else 0.0
                ),
                summary="run errored before finishing",
                detail=str(result.get("error") or _finished_error(finished_event) or "run errored"),
            )
        )

    anomalies.sort(key=lambda a: a.seq)
    failure_point = _pick_failure_point(trace.outcome, anomalies)

    blocked = sum(1 for t in tool_calls if t.blocked)
    failed = sum(1 for t in tool_calls if t.failed)
    commands = sum(1 for t in tool_calls if t.tool in _COMMAND_TOOLS and t.allowed)

    return ReplayedRun(
        trace_id=trace.trace_id,
        schema_version=trace.schema_version,
        task_id=str(trace.task.get("id", "")),
        task_title=str(trace.task.get("title", "")),
        agent=trace.agent,
        outcome=trace.outcome,
        started_at_iso=trace.started_at_iso,
        duration_seconds=trace.duration_seconds,
        timeline=trace.events,
        tool_calls=tuple(tool_calls),
        tests=tests,
        diff=diff,
        anomalies=tuple(anomalies),
        failure_point=failure_point,
        tool_call_count=len(tool_calls),
        blocked_count=blocked,
        failed_tool_count=failed,
        command_count=commands,
    )


# -- internals --------------------------------------------------------------


def _tool_call_view(ev: TraceEvent) -> ToolCallView:
    d = ev.data
    return ToolCallView(
        step_index=_opt_int(d.get("index")),
        seq=ev.seq,
        elapsed_seconds=ev.elapsed_seconds,
        tool=str(d.get("tool", "")),
        args=dict(d.get("args", {})),
        allowed=bool(d.get("allowed", True)),
        ok=d.get("ok"),
        category=d.get("category"),
        exit_code=_opt_int(d.get("exit_code")),
        summary=ev.summary,
        error=d.get("error"),
    )


def _resolve_tests(
    result: Mapping[str, Any], tests_event: TraceEvent | None
) -> Mapping[str, Any] | None:
    """Full embedded test result if present, else the compact event payload."""
    embedded = result.get("tests")
    if embedded is not None:
        return embedded
    return dict(tests_event.data) if tests_event is not None else None


def _resolve_diff(
    result: Mapping[str, Any], diff_event: TraceEvent | None
) -> Mapping[str, Any] | None:
    """Full embedded diff (with the unified text) if present, else the event."""
    embedded = result.get("diff")
    if embedded is not None:
        return embedded
    return dict(diff_event.data) if diff_event is not None else None


def _tests_detail(tests: Mapping[str, Any]) -> str:
    if tests.get("timed_out"):
        return "test command timed out"
    return f"test command exited {tests.get('exit_code')}"


def _finished_error(finished_event: TraceEvent | None) -> str | None:
    if finished_event is None:
        return None
    return finished_event.data.get("error")


def _pick_failure_point(outcome: str | None, anomalies: Sequence[Anomaly]) -> Anomaly | None:
    """Choose the anomaly that best explains the run's verdict.

    A run that passed or was not scored has no failure point, even if it logged
    anomalies along the way (a blocked call the agent recovered from is recorded
    but did not sink the run). Otherwise prefer the verdict-determining cause —
    the terminal ``run_error``, then the scoring ``tests_failed`` — and fall back
    to the earliest anomaly (anomalies are sorted by sequence) as the root signal.
    """
    if outcome in (RunOutcome.PASSED, RunOutcome.NOT_SCORED):
        return None
    if not anomalies:
        return None
    for kind in ("run_error", "tests_failed"):
        for a in anomalies:
            if a.kind == kind:
                return a
    return anomalies[0]


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
