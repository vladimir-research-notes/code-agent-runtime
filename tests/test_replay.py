"""Tests for the Milestone 6 replay and summarise tooling.

CPU-only and offline. A deterministic ``FakeClock`` (the same shape as the trace
tests use) makes every reconstruction reproducible. Coverage:

- replay of a passing run — timeline, tool calls, counts, no failure point;
- replay of a failing run — the mock agent leaves tests failing, and
  ``tests_failed`` is the chosen failure point;
- replay of an errored run — workspace preparation failed, so the timeline is
  just ``run_started`` / ``run_finished`` and ``run_error`` is the failure point;
- a blocked tool call surfaces as an anomaly but, on a run that still passed,
  does **not** become the failure point (the "scores hide failure modes" case);
- ``ReplayedRun.to_dict`` is JSON-serialisable;
- ``summarize_trace`` / ``trace_to_markdown`` render the key facts;
- the ``trace show`` / ``trace report`` CLI (text, ``--json``, ``--out``, and the
  missing-file error path).

Tests that exercise the test command run ``python3 -m pytest`` in a workspace;
they are CPU-only and need no network. Diff assertions skip when ``git`` is
absent.
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
from code_agent_runtime.agents.solutions import SOLUTIONS
from code_agent_runtime.tools import ToolCall
from code_agent_runtime.traces.recorder import Clock

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
HAS_GIT = shutil.which("git") is not None
BUGFIX = "bugfix/sum-range-off-by-one"


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


class FakeClock(Clock):
    """Deterministic clock: wall and monotonic each advance by a fixed step."""

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


def _record(task: TK.Task, agent: A.Agent, **cfg: object) -> TR.Trace:
    config = R.RunConfig(**cfg) if cfg else None
    _, trace = TR.record_run(task, agent, config=config, clock=FakeClock())
    return trace


# --- replay of a passing run -----------------------------------------------


def test_replay_passing_run_reconstructs_timeline_and_tools() -> None:
    task = _load(BUGFIX)
    trace = _record(task, A.build_scripted_agent(task))
    run = TR.replay_trace(trace)

    assert run.outcome == R.RunOutcome.PASSED
    assert run.trace_id == trace.trace_id
    assert run.task_id == BUGFIX
    assert run.agent == "scripted"

    # Three agent tool calls (read_file, search_repo, apply_patch); none are
    # command tools and none were blocked or failed.
    assert run.tool_call_count == 3
    assert [t.tool for t in run.tool_calls] == ["read_file", "search_repo", "apply_patch"]
    assert run.blocked_count == 0
    assert run.failed_tool_count == 0
    assert run.command_count == 0
    assert all(t.allowed and t.ok for t in run.tool_calls)

    # Timeline is the full ordered event stream; tests passed; no failure point.
    kinds = [e.kind for e in run.timeline]
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    assert run.tests is not None and run.tests.get("passed") is True
    assert run.anomalies == ()
    assert run.failure_point is None
    assert run.passed is True


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_replay_passing_run_has_diff() -> None:
    task = _load(BUGFIX)
    run = TR.replay_trace(_record(task, A.build_scripted_agent(task)))
    assert run.diff is not None
    assert run.diff.get("insertions", 0) >= 1
    # The embedded diff carries the full unified text, not just counts.
    assert "summation.py" in (run.diff.get("diff") or "")


# --- replay of a failing run -----------------------------------------------


def test_replay_failing_run_points_at_tests() -> None:
    task = _load(BUGFIX)
    # The null mock agent makes no edits, so the buggy fixture still fails.
    run = TR.replay_trace(_record(task, A.MockAgent()))

    assert run.outcome == R.RunOutcome.FAILED
    assert run.tool_call_count == 0
    assert run.tests is not None and run.tests.get("passed") is False

    kinds = {a.kind for a in run.anomalies}
    assert "tests_failed" in kinds
    assert run.failure_point is not None
    assert run.failure_point.kind == "tests_failed"
    # The failure point is located on the tests_ran event of the timeline.
    assert run.failure_point.phase == R.RunPhase.TESTING


# --- replay of an errored run ----------------------------------------------


def test_replay_errored_run_points_at_run_error() -> None:
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
    run = TR.replay_trace(_record(task, A.MockAgent()))

    assert run.outcome == R.RunOutcome.ERROR
    assert [e.kind for e in run.timeline] == ["run_started", "run_finished"]
    assert run.tests is None and run.diff is None
    assert run.failure_point is not None
    assert run.failure_point.kind == "run_error"
    assert run.failure_point.detail  # carries the workspace-preparation error


# --- a blocked tool is an anomaly but not always the failure point ----------


def test_blocked_tool_is_anomaly_but_not_failure_on_passing_run() -> None:
    """The case that motivates trace-level analysis: a run can pass while still
    having logged a failure mode (a blocked tool call) that the verdict hides."""
    task = _load(BUGFIX)
    # The solution's real steps fix the bug; appending a run_shell call (not in
    # this task's allowed_tools) adds a blocked call that does not run.
    solution_calls = SOLUTIONS[BUGFIX](task)
    script = list(solution_calls) + [ToolCall("run_shell", {"command": ["echo", "hi"]})]
    agent = A.ScriptedAgent(script, name="scripted")

    run = TR.replay_trace(_record(task, agent))

    assert run.outcome == R.RunOutcome.PASSED  # the fix still landed
    assert run.blocked_count == 1
    blocked = [a for a in run.anomalies if a.kind == "blocked_tool"]
    assert len(blocked) == 1
    # A passing run has no failure point even though an anomaly was recorded.
    assert run.failure_point is None
    # The blocked call is visible in the reconstructed tool calls.
    assert any(t.tool == "run_shell" and t.blocked for t in run.tool_calls)


# --- structured output -----------------------------------------------------


def test_replayed_run_to_dict_is_json_serialisable() -> None:
    task = _load(BUGFIX)
    run = TR.replay_trace(_record(task, A.build_scripted_agent(task)))
    payload = json.loads(json.dumps(run.to_dict()))
    assert payload["trace_id"] == run.trace_id
    assert payload["counts"]["tool_calls"] == run.tool_call_count
    assert len(payload["timeline"]) == len(run.timeline)


# --- text + markdown rendering ---------------------------------------------


def test_summarize_text_for_failing_run() -> None:
    task = _load(BUGFIX)
    text = TR.summarize_trace(_record(task, A.MockAgent()))
    assert "Trace:" in text
    assert BUGFIX in text
    assert "failed" in text
    assert "timeline" in text
    # The failure point is called out.
    assert "tests_failed" in text and "failure point" in text


def test_markdown_report_structure() -> None:
    task = _load(BUGFIX)
    md_pass = TR.trace_to_markdown(_record(task, A.build_scripted_agent(task)))
    assert md_pass.startswith("# Trace report:")
    for heading in ("## Verdict", "## Timeline", "## Tool calls"):
        assert heading in md_pass
    assert "no failure point" in md_pass

    md_fail = TR.trace_to_markdown(_record(task, A.MockAgent()))
    assert "**Failure point:**" in md_fail
    assert "`tests_failed`" in md_fail


def test_markdown_table_cells_escape_pipes() -> None:
    # A summary containing a pipe must not break the Markdown table columns.
    ev = TR.TraceEvent(
        seq=0, kind="run_started", phase="preparing_workspace", timestamp=0.0,
        elapsed_seconds=0.0, summary="a | b", data={},
    )
    trace = TR.Trace(
        schema_version=TR.SCHEMA_VERSION, trace_id="t", task={"id": "x", "title": "y"},
        agent="mock", config={}, workspace=None, started_at=0.0, started_at_iso="iso",
        finished_at=1.0, duration_seconds=1.0, outcome=R.RunOutcome.NOT_SCORED,
        events=(ev,), result=None,
    )
    md = TR.trace_to_markdown(trace)
    assert "a \\| b" in md


# --- CLI -------------------------------------------------------------------


def _write_trace_via_cli(tmp_path: Path, task_id: str = BUGFIX) -> Path:
    dest = tmp_path / "run.trace.json"
    rc = cli.main(["run", task_id, "--dir", str(TASKS_DIR), "--trace", str(dest)])
    assert rc == 0 and dest.is_file()
    return dest


def test_cli_trace_show_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = _write_trace_via_cli(tmp_path)
    capsys.readouterr()  # drop the run's output
    rc = cli.main(["trace", "show", str(dest)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Trace:" in out and BUGFIX in out and "timeline" in out


def test_cli_trace_show_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = _write_trace_via_cli(tmp_path)
    capsys.readouterr()
    rc = cli.main(["trace", "show", str(dest), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["task_id"] == BUGFIX
    assert payload["outcome"] == R.RunOutcome.PASSED


def test_cli_trace_report_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = _write_trace_via_cli(tmp_path)
    capsys.readouterr()
    rc = cli.main(["trace", "report", str(dest)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("# Trace report:")


def test_cli_trace_report_out_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dest = _write_trace_via_cli(tmp_path)
    capsys.readouterr()
    out_path = tmp_path / "report.md"
    rc = cli.main(["trace", "report", str(dest), "--out", str(out_path)])
    err = capsys.readouterr().err
    assert rc == 0
    assert out_path.is_file()
    assert out_path.read_text(encoding="utf-8").startswith("# Trace report:")
    assert "report written:" in err


def test_cli_trace_show_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["trace", "show", "/no/such/trace.json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "could not load trace" in err
