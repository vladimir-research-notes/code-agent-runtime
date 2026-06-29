"""The structured run-trace schema (Milestone 5).

A *trace* is the complete, replayable record of one run: enough to reconstruct
what the task was, what the agent did, what the runtime observed, and *when* —
without re-executing anything. These types are pure, JSON-serialisable data, in
the same spirit as :mod:`code_agent_runtime.runtime.state`: nothing here records
an event, runs a clock, or touches the filesystem. The recorder
(:mod:`.recorder`) builds a :class:`Trace`; replay/summarise tooling (Milestone
6) consumes one.

What a trace carries (every item the plan names):

- **task metadata** — id, title, prompt, scoring method, test command, allowed
  tools, fixture, limits (the ``task`` block);
- **workspace metadata** — root, fixture, git status (the ``workspace`` block);
- **agent actions and tool calls** — the timestamped ``events`` timeline;
- **command stdout/stderr, file diffs, test results, exit status** — embedded in
  ``result`` (a :class:`~code_agent_runtime.runtime.state.RunResult` dict), which
  holds the full tool payloads so the lightweight events need not duplicate them;
- **timestamps** — wall-clock ``timestamp`` per event, ``elapsed_seconds`` since
  the run started, and run-level ``started_at`` / ``finished_at`` /
  ``duration_seconds``. This is where wall-clock timing enters the system: the
  tools and the ``RunResult`` are deliberately timing-free so they stay
  deterministic; the trace is the one artifact that is *allowed* to be temporal.

Honesty note: traces are **not redacted**. Captured command output is stored as
captured, so a trace may contain whatever a command printed (including secrets a
task's commands happen to surface). Redaction belongs with the secret scanner in
Milestone 7; until then, do not persist traces of untrusted commands to a shared
location. This is recorded as a limitation, not a solved problem.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: Trace-schema version. Bumped only on a breaking change to the on-disk shape,
#: so a reader can refuse (or migrate) a trace it does not understand.
SCHEMA_VERSION = 1

#: Closed vocabulary of trace event kinds, in roughly the order they occur. The
#: recorder validates against this set so a typo cannot enter a trace silently.
TRACE_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "run_started",         # the run began (carries task/agent/config echo)
        "workspace_prepared",  # fixture copied + (maybe) git-initialised
        "tool_call",           # the agent invoked a tool (allowed or blocked)
        "agent_finish",        # the agent declared itself done
        "tests_ran",           # the task's test command executed
        "diff_captured",       # the final workspace diff was captured
        "scored",              # the run was scored
        "run_finished",        # terminal event (carries the outcome)
    }
)


@dataclass(frozen=True)
class TraceEvent:
    """One timestamped event in a run's timeline.

    ``timestamp`` is wall-clock epoch seconds (UTC); ``elapsed_seconds`` is
    monotonic time since the run started, which is the right clock for durations
    because it is immune to wall-clock adjustments. ``data`` is the event-specific
    payload — kept compact, since the full tool payloads live in ``Trace.result``.
    """

    seq: int
    kind: str
    phase: str
    timestamp: float
    elapsed_seconds: float
    summary: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": self.summary,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TraceEvent:
        return cls(
            seq=int(d["seq"]),
            kind=str(d["kind"]),
            phase=str(d["phase"]),
            timestamp=float(d["timestamp"]),
            elapsed_seconds=float(d["elapsed_seconds"]),
            summary=str(d["summary"]),
            data=dict(d.get("data", {})),
        )


@dataclass(frozen=True)
class Trace:
    """The complete, JSON-serialisable record of one run.

    ``result`` embeds the run's
    :meth:`~code_agent_runtime.runtime.state.RunResult.to_dict`, so the full tool
    outputs (command stdout/stderr, the final diff, test results, exit status)
    are captured exactly once there, while ``events`` provide the timestamped
    timeline that points into them. ``workspace`` is ``None`` when the run failed
    before a workspace was prepared.
    """

    schema_version: int
    trace_id: str
    task: Mapping[str, Any]
    agent: str
    config: Mapping[str, Any]
    workspace: Mapping[str, Any] | None
    started_at: float
    started_at_iso: str
    finished_at: float | None
    duration_seconds: float | None
    outcome: str | None
    events: tuple[TraceEvent, ...]
    result: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "task": dict(self.task),
            "agent": self.agent,
            "config": dict(self.config),
            "workspace": dict(self.workspace) if self.workspace is not None else None,
            "started_at": self.started_at,
            "started_at_iso": self.started_at_iso,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "events": [e.to_dict() for e in self.events],
            "result": dict(self.result) if self.result is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Trace:
        """Reconstruct a :class:`Trace` from its serialised form.

        Used to load a persisted trace (and by the schema round-trip tests). It
        does not re-validate field semantics beyond the shape — a trace this
        runtime wrote is trusted to be well-formed.
        """
        workspace = d.get("workspace")
        result = d.get("result")
        return cls(
            schema_version=int(d["schema_version"]),
            trace_id=str(d["trace_id"]),
            task=dict(d["task"]),
            agent=str(d["agent"]),
            config=dict(d.get("config", {})),
            workspace=dict(workspace) if workspace is not None else None,
            started_at=float(d["started_at"]),
            started_at_iso=str(d["started_at_iso"]),
            finished_at=float(d["finished_at"]) if d.get("finished_at") is not None else None,
            duration_seconds=(
                float(d["duration_seconds"]) if d.get("duration_seconds") is not None else None
            ),
            outcome=d.get("outcome"),
            events=tuple(TraceEvent.from_dict(e) for e in d.get("events", [])),
            result=dict(result) if result is not None else None,
        )
