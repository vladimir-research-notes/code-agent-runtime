"""Tests for the Milestone 5 trace recorder and schema.

CPU-only and offline. A deterministic fake clock makes every trace reproducible,
so we can assert on timestamps, ordering, and ids exactly. Coverage:

- schema round-trip (``Trace``/``TraceEvent`` ``to_dict``/``from_dict``);
- the recorder lifecycle (event ordering, sequence numbers, elapsed times);
- ``record_run`` over the shipped fixtures (full timeline, embedded result,
  determinism vs. an untraced run);
- the error path (a run that fails workspace preparation still yields a trace);
- persistence (``write_trace``/``load_trace``) for both file and directory dests;
- the ``run --trace`` CLI surface.

Tests that need ``git`` skip when it is absent (the diff-captured event).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from code_agent_runtime import agents as A
from code_agent_runtime import cli
from code_agent_runtime import runtime as R
from code_agent_runtime import tasks as TK
from code_agent_runtime import traces as TR
from code_agent_runtime.traces.recorder import Clock

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
HAS_GIT = shutil.which("git") is not None


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


class FakeClock(Clock):
    """Deterministic clock: wall and monotonic each advance by a fixed step.

    Keeping wall and monotonic on separate counters mirrors the real split and
    makes the asserted timestamps independent of the host clock.
    """

    def __init__(self, *, start_wall: float = 1_700_000_000.0) -> None:
        self._wall = start_wall
        self._mono = 0.0

    def wall(self) -> float:
        v = self._wall
        self._wall += 1.0
        return v

    def monotonic(self) -> float:
        v = self._mono
        self._mono += 0.5
        return v


# --- schema round-trip -----------------------------------------------------


def test_trace_event_roundtrips() -> None:
    ev = TR.TraceEvent(
        seq=3, kind="tool_call", phase="agent_loop", timestamp=1.5,
        elapsed_seconds=0.25, summary="did a thing", data={"tool": "read_file"},
    )
    assert TR.TraceEvent.from_dict(ev.to_dict()) == ev


def test_trace_roundtrips_through_dict() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    again = TR.Trace.from_dict(trace.to_dict())
    assert again.to_dict() == trace.to_dict()
    assert again.events == trace.events


def test_trace_is_json_serialisable() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    assert json.dumps(trace.to_dict())  # does not raise


# --- recorder lifecycle ----------------------------------------------------


def test_recorder_requires_start_before_events() -> None:
    rec = TR.TraceRecorder(clock=FakeClock())
    ws = R.prepare_workspace(_load("bugfix/sum-range-off-by-one"), init_git=False)
    try:
        with pytest.raises(RuntimeError):
            rec.workspace_prepared(ws)
    finally:
        ws.cleanup()


def test_events_have_increasing_seq_and_elapsed() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    seqs = [e.seq for e in trace.events]
    assert seqs == list(range(len(trace.events)))
    elapsed = [e.elapsed_seconds for e in trace.events]
    assert elapsed == sorted(elapsed)  # monotonic, non-decreasing
    assert all(k in TR.TRACE_EVENT_KINDS for k in (e.kind for e in trace.events))


# --- record_run over fixtures ----------------------------------------------


def test_trace_timeline_for_bugfix() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())

    assert trace.schema_version == TR.SCHEMA_VERSION
    assert trace.outcome == R.RunOutcome.PASSED == result.outcome
    # Deterministic id and ISO start from the fake clock.
    assert trace.trace_id == "bugfix_sum-range-off-by-one-1700000000.000"
    assert trace.started_at == 1_700_000_000.0
    assert trace.started_at_iso.startswith("2023-11-14T")
    assert trace.duration_seconds is not None and trace.duration_seconds > 0

    kinds = [e.kind for e in trace.events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert "workspace_prepared" in kinds
    assert kinds.count("tool_call") == result.tool_call_count == 3
    assert "agent_finish" in kinds
    assert "tests_ran" in kinds
    assert "scored" in kinds

    # Task + config metadata blocks are present and faithful.
    assert trace.task["id"] == "bugfix/sum-range-off-by-one"
    assert trace.task["prompt"] == task.prompt
    assert trace.config["max_steps"] == R.RunConfig().max_steps
    assert trace.agent == "scripted"

    # The full result is embedded (command output, tests, score, steps).
    assert trace.result is not None
    assert trace.result["outcome"] == R.RunOutcome.PASSED
    assert len(trace.result["steps"]) == len(result.steps)


def test_trace_outcome_matches_untraced_run() -> None:
    """Tracing must not change the run: outcome and counts are identical."""
    task = _load("bugfix/sum-range-off-by-one")
    plain = R.run_task(task, A.build_scripted_agent(task))
    traced, _ = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    assert plain.outcome == traced.outcome
    assert plain.tool_call_count == traced.tool_call_count
    assert plain.command_count == traced.command_count


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_trace_has_diff_captured_event() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    diff_events = [e for e in trace.events if e.kind == "diff_captured"]
    assert len(diff_events) == 1
    assert diff_events[0].data["insertions"] >= 1
    assert trace.workspace is not None and trace.workspace["git"] is True


def test_trace_explicit_id_is_used() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(
        task, A.build_scripted_agent(task), clock=FakeClock(), trace_id="custom-id"
    )
    assert trace.trace_id == "custom-id"


# --- error path ------------------------------------------------------------


def test_trace_captures_error_run() -> None:
    task = TK.validate_task_dict(
        {
            "version": 1,
            "id": "tmp/missing",
            "title": "t",
            "prompt": "p",
            "fixture": "/nonexistent/path/xyz",
            "scoring_method": "none",
        }
    )
    result, trace = TR.record_run(task, A.MockAgent(), clock=FakeClock())
    assert result.outcome == R.RunOutcome.ERROR
    kinds = [e.kind for e in trace.events]
    assert kinds == ["run_started", "run_finished"]  # failed before workspace prep
    assert trace.workspace is None
    finished = trace.events[-1]
    assert finished.data["outcome"] == R.RunOutcome.ERROR
    assert trace.result is not None and trace.result["error"]


# --- persistence -----------------------------------------------------------


def test_write_and_load_trace_file(tmp_path: Path) -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    dest = tmp_path / "run.trace.json"
    written = TR.write_trace(trace, dest)
    assert written == dest and dest.is_file()
    loaded = TR.load_trace(dest)
    assert loaded.to_dict() == trace.to_dict()


def test_write_trace_to_directory_uses_trace_id(tmp_path: Path) -> None:
    task = _load("bugfix/sum-range-off-by-one")
    _, trace = TR.record_run(task, A.build_scripted_agent(task), clock=FakeClock())
    written = TR.write_trace(trace, tmp_path / "out")
    assert written.name == f"{trace.trace_id}{TR.TRACE_SUFFIX}"
    assert written.parent.name == "out" and written.is_file()


# --- CLI -------------------------------------------------------------------


def test_cli_run_trace_writes_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = tmp_path / "cli.trace.json"
    rc = cli.main(
        ["run", "bugfix/sum-range-off-by-one", "--dir", str(TASKS_DIR), "--trace", str(dest)]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "trace written:" in captured.err
    assert dest.is_file()
    trace = TR.load_trace(dest)
    assert trace.outcome == R.RunOutcome.PASSED
    assert trace.task["id"] == "bugfix/sum-range-off-by-one"


def test_cli_run_trace_to_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "tracedir"
    rc = cli.main(
        ["run", "bugfix/sum-range-off-by-one", "--dir", str(TASKS_DIR), "--trace", str(out)]
    )
    assert rc == 0
    written = list(out.glob(f"*{TR.TRACE_SUFFIX}"))
    assert len(written) == 1
