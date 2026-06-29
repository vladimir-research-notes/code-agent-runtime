"""Structured run tracing (Milestone 5).

Every run can be recorded as a structured, JSON-serialisable :class:`Trace`: the
task and workspace metadata, the timestamped timeline of agent actions and tool
calls, and the full embedded result (command output, the final diff, test
results, exit status). A trace is the evidence behind a reported result and the
input to replay/summarise tooling (Milestone 6).

Public API:

- :class:`Trace`, :class:`TraceEvent`, :data:`SCHEMA_VERSION`,
  :data:`TRACE_EVENT_KINDS` — the schema.
- :class:`TraceRecorder`, :class:`Clock` — the recorder the runtime drives, with
  an injectable clock for deterministic tests.
- :func:`record_run` — run a task with tracing and get ``(result, trace)``.
- :func:`write_trace`, :func:`load_trace` — persist/load a trace as JSON.
- :func:`replay_trace`, :class:`ReplayedRun`, :class:`ToolCallView`,
  :class:`Anomaly` — reconstruct a run from a stored trace without re-executing
  (Milestone 6: action timeline, tool calls, diff, tests, failure point).
- :func:`summarize_trace`, :func:`trace_to_markdown` — render a reconstructed run
  as a text summary or a Markdown report.

Tracing is opt-in and side-effect-free for untraced runs: the runtime loop only
records when a recorder is supplied. Captured output is **not** redacted yet —
see the schema module and ``docs/SECURITY_MODEL.md`` (redaction is Milestone 7).
"""

from __future__ import annotations

from .recorder import Clock, TraceRecorder, default_trace_id
from .replay import ANOMALY_KINDS, Anomaly, ReplayedRun, ToolCallView, replay_trace
from .schema import SCHEMA_VERSION, TRACE_EVENT_KINDS, Trace, TraceEvent
from .store import TRACE_SUFFIX, load_trace, record_run, write_trace
from .summarize import summarize_trace, trace_to_markdown

__all__ = [
    "Trace",
    "TraceEvent",
    "SCHEMA_VERSION",
    "TRACE_EVENT_KINDS",
    "TraceRecorder",
    "Clock",
    "default_trace_id",
    "record_run",
    "write_trace",
    "load_trace",
    "TRACE_SUFFIX",
    "replay_trace",
    "ReplayedRun",
    "ToolCallView",
    "Anomaly",
    "ANOMALY_KINDS",
    "summarize_trace",
    "trace_to_markdown",
]
