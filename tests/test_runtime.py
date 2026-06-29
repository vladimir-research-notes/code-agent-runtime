"""Tests for the Milestone 4 runtime state machine and agents.

CPU-only and offline. Unit tests cover the agent interface (mock null baseline,
scripted replay, script exhaustion, action coercion), workspace preparation,
allowed-tool gating, and scoring. Integration tests drive the full loop over the
shipped fixtures: the scripted agent must take ``bugfix/sum-range-off-by-one``
from failing tests to passing and capture the final diff, while the mock agent
must leave it failing. Tests needing ``git`` skip when it is absent.
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
from code_agent_runtime import tools as T
from code_agent_runtime.runtime import execution

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
HAS_GIT = shutil.which("git") is not None


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


# --- agent interface -------------------------------------------------------


def test_mock_agent_finishes_immediately() -> None:
    agent = A.MockAgent()
    action = agent.propose(A.Observation(task=_load("bugfix/sum-range-off-by-one"), step=0))
    assert agent.name == "mock"
    assert action.is_finish and action.call is None


def test_scripted_agent_replays_then_finishes() -> None:
    calls = [T.ToolCall("read_file", {"path": "x"}), ("search_repo", {"query": "y"})]
    agent = A.ScriptedAgent(calls)
    task = _load("bugfix/sum-range-off-by-one")
    agent.reset(task)
    first = agent.propose(A.Observation(task=task, step=0))
    second = agent.propose(A.Observation(task=task, step=1))
    third = agent.propose(A.Observation(task=task, step=2))
    assert first.kind == "tool" and first.call.tool == "read_file"
    assert second.kind == "tool" and second.call.tool == "search_repo"
    assert third.is_finish  # script exhausted


def test_scripted_agent_reset_rewinds() -> None:
    agent = A.ScriptedAgent([T.ToolCall("read_file", {"path": "x"})])
    task = _load("bugfix/sum-range-off-by-one")
    assert agent.propose(A.Observation(task=task, step=0)).kind == "tool"
    assert agent.propose(A.Observation(task=task, step=1)).is_finish
    agent.reset(task)
    assert agent.propose(A.Observation(task=task, step=0)).kind == "tool"


def test_scripted_agent_rejects_bad_step() -> None:
    with pytest.raises(TypeError):
        A.ScriptedAgent([123])


def test_agent_action_to_dict_roundtrips() -> None:
    action = A.AgentAction.tool("read_file", {"path": "f"}, message="why")
    assert json.dumps(action.to_dict())  # serialisable
    assert A.AgentAction.finish("done").to_dict()["call"] is None


# --- solutions -------------------------------------------------------------


def test_has_solution_for_shipped_tasks() -> None:
    assert A.has_solution("bugfix/sum-range-off-by-one")
    assert A.has_solution("cli/add-shout-flag")
    assert not A.has_solution("security/unsafe-command-demo")


def test_build_scripted_agent_unknown_task_raises() -> None:
    task = _load("security/unsafe-command-demo")
    with pytest.raises(KeyError):
        A.build_scripted_agent(task)


# --- workspace preparation -------------------------------------------------


def test_prepare_workspace_copies_fixture(tmp_path: Path) -> None:
    task = _load("bugfix/sum-range-off-by-one")
    ws = execution.prepare_workspace(task, init_git=False)
    try:
        assert (ws.root / "summation.py").is_file()
        assert (ws.root / "test_summation.py").is_file()
        # The committed fixture is never the workspace.
        assert ws.root.resolve() != ws.fixture.resolve()
    finally:
        ws.cleanup()
    assert not ws.root.exists()


def test_prepare_workspace_skips_caches(tmp_path: Path) -> None:
    # Build a throwaway fixture with a __pycache__ dir and point a task at it.
    fixture = tmp_path / "fix"
    (fixture / "__pycache__").mkdir(parents=True)
    (fixture / "__pycache__" / "junk.pyc").write_bytes(b"\x00")
    (fixture / "mod.py").write_text("x = 1\n", encoding="utf-8")
    task = TK.validate_task_dict(
        {
            "version": 1,
            "id": "tmp/x",
            "title": "t",
            "prompt": "p",
            "fixture": str(fixture),
            "scoring_method": "none",
        }
    )
    ws = execution.prepare_workspace(task, init_git=False)
    try:
        assert (ws.root / "mod.py").is_file()
        assert not (ws.root / "__pycache__").exists()
    finally:
        ws.cleanup()


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_prepare_workspace_inits_git() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    ws = execution.prepare_workspace(task, init_git=True)
    try:
        assert ws.git is True
        assert (ws.root / ".git").is_dir()
    finally:
        ws.cleanup()


# --- allowed-tool gating ---------------------------------------------------


def test_gating_blocks_disallowed_tool(tmp_path: Path) -> None:
    reg = T.build_registry()
    ctx = T.ToolContext.for_dir(tmp_path)
    result, allowed = execution.dispatch_agent_call(
        reg, {"read_file"}, T.ToolCall("run_shell", {"command": ["echo", "hi"]}), ctx
    )
    assert allowed is False
    assert not result.ok and result.category == "blocked"
    assert "not permitted" in result.error


def test_gating_allows_permitted_tool(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    reg = T.build_registry()
    ctx = T.ToolContext.for_dir(tmp_path)
    result, allowed = execution.dispatch_agent_call(
        reg, {"read_file"}, T.ToolCall("read_file", {"path": "f.txt"}), ctx
    )
    assert allowed is True and result.ok and result.data["content"] == "hi"


# --- scoring ---------------------------------------------------------------


def test_score_none_is_not_scored() -> None:
    from code_agent_runtime.runtime.agent_loop import _score

    task = _load("security/unsafe-command-demo")
    score = _score(task, None)
    assert score["outcome"] == R.RunOutcome.NOT_SCORED and score["passed"] is None


def test_score_test_command_pass_fail() -> None:
    from code_agent_runtime.runtime.agent_loop import _score

    task = _load("bugfix/sum-range-off-by-one")
    assert _score(task, {"passed": True})["outcome"] == R.RunOutcome.PASSED
    assert _score(task, {"passed": False})["outcome"] == R.RunOutcome.FAILED
    # Missing test data is a failure, not a crash.
    assert _score(task, None)["outcome"] == R.RunOutcome.FAILED


# --- full runs (integration) -----------------------------------------------


def test_scripted_agent_completes_bugfix() -> None:
    """The Milestone 4 acceptance run: scripted agent fixes the smoke task."""
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task))

    assert result.outcome == R.RunOutcome.PASSED
    assert result.phase_reached == R.RunPhase.DONE
    assert result.passed
    assert result.tests is not None and result.tests["passed"] is True
    # read_file, search_repo, apply_patch (+ the finish step is not a tool call).
    assert result.tool_call_count == 3
    assert result.command_count == 0  # the agent ran no exec-category tools
    # Every agent tool call was permitted and succeeded.
    tool_steps = [s for s in result.steps if s.action_kind == "tool"]
    assert all(s.allowed and s.result.ok for s in tool_steps)
    # Workspace is ephemeral and cleaned up by default.
    assert not result.kept_workspace


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_scripted_run_captures_final_diff() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task))
    assert result.git is True
    assert result.diff is not None
    assert result.diff["insertions"] >= 1
    assert any(f["path"] == "summation.py" for f in result.diff["files"])


def test_mock_agent_leaves_bugfix_failing() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.MockAgent())
    assert result.outcome == R.RunOutcome.FAILED
    assert result.tool_call_count == 0
    assert result.tests is not None and result.tests["passed"] is False


def test_scripted_agent_completes_cli_task() -> None:
    task = _load("cli/add-shout-flag")
    result = R.run_task(task, A.build_scripted_agent(task))
    assert result.outcome == R.RunOutcome.PASSED
    assert result.tests is not None and result.tests["passed"] is True


def test_security_task_runs_not_scored() -> None:
    task = _load("security/unsafe-command-demo")
    result = R.run_task(task, A.MockAgent())
    assert result.outcome == R.RunOutcome.NOT_SCORED
    assert result.tests is None  # no test_command on this task


def test_run_result_is_json_serialisable() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task))
    assert json.dumps(result.to_dict())  # does not raise


def test_keep_workspace_leaves_dir() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.MockAgent(), config=R.RunConfig(keep_workspace=True, run_tests=False))
    try:
        assert result.kept_workspace
        assert Path(result.workspace).is_dir()
    finally:
        shutil.rmtree(result.workspace, ignore_errors=True)


def test_max_steps_caps_the_loop() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    # A script longer than max_steps must stop early with the right reason.
    long_script = [T.ToolCall("read_file", {"path": "summation.py"})] * 5
    agent = A.ScriptedAgent(long_script)
    result = R.run_task(task, agent, config=R.RunConfig(max_steps=2, run_tests=False))
    assert len([s for s in result.steps if s.action_kind == "tool"]) == 2
    assert "max_steps" in result.stop_reason


def test_workspace_error_yields_error_outcome() -> None:
    # A task whose fixture is removed after load surfaces as an error outcome.
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
    result = R.run_task(task, A.MockAgent())
    assert result.outcome == R.RunOutcome.ERROR
    assert result.phase_reached == R.RunPhase.PREPARING
    assert result.error


# --- report ----------------------------------------------------------------


def test_format_run_report_mentions_key_fields() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task))
    text = R.format_run_report(result)
    assert "Run report: bugfix/sum-range-off-by-one" in text
    assert "outcome" in text and "scripted" in text


# --- CLI -------------------------------------------------------------------


def test_cli_run_scripted_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", "bugfix/sum-range-off-by-one", "--dir", str(TASKS_DIR)])
    out = capsys.readouterr().out
    assert rc == 0 and "outcome      : passed" in out


def test_cli_run_mock_fails(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", "bugfix/sum-range-off-by-one", "--agent", "mock", "--dir", str(TASKS_DIR)])
    out = capsys.readouterr().out
    assert rc == 1 and "outcome      : failed" in out


def test_cli_run_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(
        ["run", "bugfix/sum-range-off-by-one", "--dir", str(TASKS_DIR), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["outcome"] == "passed"
    assert payload["task_id"] == "bugfix/sum-range-off-by-one"


def test_cli_run_no_solution_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(
        ["run", "security/unsafe-command-demo", "--dir", str(TASKS_DIR)]
    )
    assert rc == 1 and "no built-in scripted solution" in capsys.readouterr().err


def test_cli_run_unknown_task_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", "no/such-task", "--dir", str(TASKS_DIR)])
    assert rc == 1 and "no task found" in capsys.readouterr().err
