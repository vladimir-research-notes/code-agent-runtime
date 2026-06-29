"""Persisting and loading traces, and the convenience run-and-trace wrapper.

These are the small I/O helpers around the pure schema. A trace is stored as
indented JSON so it is diff-friendly and human-inspectable; this is the format
the replay/summarise tooling (Milestone 6) will read.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..agents import Agent
from ..tasks import Task
from ..runtime.state import RunConfig, RunResult
from .recorder import Clock, TraceRecorder
from .schema import Trace

#: Filename suffix for a persisted trace.
TRACE_SUFFIX = ".trace.json"


def record_run(
    task: Task,
    agent: Agent,
    *,
    config: RunConfig | None = None,
    registry=None,
    workspace_dest=None,
    clock: Clock | None = None,
    trace_id: str | None = None,
) -> tuple[RunResult, Trace]:
    """Run ``agent`` over ``task`` and return ``(result, trace)``.

    A thin wrapper over :func:`code_agent_runtime.runtime.run_task` that attaches
    a :class:`TraceRecorder`. The returned :class:`RunResult` is exactly what an
    untraced run would produce (the trace is built alongside, not instead). The
    import of ``run_task`` is local to keep package import order simple and to
    make explicit that ``traces`` depends on ``runtime``, never the reverse.
    """
    from ..runtime import run_task

    recorder = TraceRecorder(clock=clock, trace_id=trace_id)
    result = run_task(
        task,
        agent,
        config=config,
        registry=registry,
        workspace_dest=workspace_dest,
        recorder=recorder,
    )
    assert recorder.trace is not None  # run_task always finishes the recorder
    return result, recorder.trace


def write_trace(trace: Trace, dest: str | Path) -> Path:
    """Write ``trace`` as JSON and return the path written.

    ``dest`` ending in ``.json`` is treated as the target file; any other path is
    treated as a directory the trace is written into as
    ``<trace_id>.trace.json``. Parent directories are created as needed.
    """
    dest = Path(dest)
    if dest.suffix == ".json":
        path = dest
    else:
        path = dest / f"{trace.trace_id}{TRACE_SUFFIX}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_trace(path: str | Path) -> Trace:
    """Load a trace previously written by :func:`write_trace`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Trace.from_dict(data)
