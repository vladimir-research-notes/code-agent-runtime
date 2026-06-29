"""Tests for the Milestone 8 eval suite runner and reports.

CPU-only and offline. Covers the suite runner over the real shipped tasks (the
agent×task matrix, skipped pairs, per-run records and their failure reasons),
deterministic timing via an injected clock, JSON round-tripping of a
``SuiteResult``, the Markdown and HTML reports, and the ``eval run`` / ``eval
report`` CLI. Assertions that depend on the captured git diff (the
``diff_constraint`` / ``custom`` scoped runs) are gated on ``git`` being present.
"""

from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest

from code_agent_runtime import cli
from code_agent_runtime import reports as RP
from code_agent_runtime import scoring as SC
from code_agent_runtime import tasks as TK

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
HAS_GIT = shutil.which("git") is not None


def _all_tasks():
    return list(TK.discover_tasks(TASKS_DIR, resolve_fixture=True))


def _fixed_clock():
    """A clock that ticks one unit per call, so each run's runtime is exactly 1.0."""
    counter = itertools.count()
    return lambda: float(next(counter))


# --- build_agent matrix ----------------------------------------------------


def test_build_agent_applicability() -> None:
    bugfix = TK.find_task(TASKS_DIR, "bugfix/sum-range-off-by-one")
    security = TK.find_task(TASKS_DIR, "security/unsafe-command-demo")
    assert SC.build_agent("mock", bugfix) is not None
    assert SC.build_agent("scripted", bugfix) is not None
    assert SC.build_agent("scripted", security) is None  # no solution
    assert SC.build_agent("probe", bugfix) is None  # no probe
    assert SC.build_agent("probe", security) is not None
    with pytest.raises(ValueError):
        SC.build_agent("bogus", bugfix)


# --- run_suite -------------------------------------------------------------


def test_run_suite_mock_and_scripted_records() -> None:
    tasks = _all_tasks()
    suite = SC.run_suite(tasks, agents=("mock", "scripted"), clock=_fixed_clock())
    by_key = {(r.task_id, r.agent): r for r in suite.records}

    # Mock leaves the bugfix failing; scripted fixes it.
    assert by_key[("bugfix/sum-range-off-by-one", "mock")].passed is False
    scripted = by_key[("bugfix/sum-range-off-by-one", "scripted")]
    assert scripted.passed is True
    assert scripted.tool_call_count == 3 and scripted.runtime_seconds == 1.0
    # A failure carries a human reason.
    assert by_key[("bugfix/sum-range-off-by-one", "mock")].failure_reason

    # 'scripted' is inapplicable to the security demo (no solution) → skipped.
    assert {"task_id": "security/unsafe-command-demo", "agent": "scripted"} in [
        dict(s) for s in suite.skipped
    ]


def test_run_suite_default_matrix_totals() -> None:
    suite = SC.run_suite(_all_tasks(), clock=_fixed_clock())
    totals = suite.totals()
    # Every record's outcome is a known verdict and totals sum to the count.
    assert sum(totals.values()) == suite.total
    assert all(r.outcome in SC.Outcome.ALL for r in suite.records)
    # The probe run on the security demo is recorded and blocks every step.
    probe = next(
        r for r in suite.records if r.task_id == "security/unsafe-command-demo" and r.agent == "probe"
    )
    assert probe.outcome == SC.Outcome.NOT_SCORED and probe.blocked_count >= 1


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_run_suite_new_scoring_methods_pass_for_scripted() -> None:
    suite = SC.run_suite(_all_tasks(), agents=("scripted",), clock=_fixed_clock())
    by_task = {r.task_id: r for r in suite.records}
    assert by_task["refactor/sum-range-diff-scope"].passed is True  # diff_constraint
    assert by_task["bugfix/sum-range-expected-files"].passed is True  # expected_files
    assert by_task["cli/add-shout-flag-custom"].passed is True  # custom composite


# --- serialisation ---------------------------------------------------------


def test_suite_result_json_round_trip(tmp_path: Path) -> None:
    suite = SC.run_suite(_all_tasks(), agents=("mock",), clock=_fixed_clock(), label="rt")
    path = tmp_path / "raw" / "eval.json"
    SC.write_suite_result(suite, path)
    assert path.is_file()
    loaded = SC.load_suite_result(path)
    assert loaded.label == "rt"
    assert loaded.total == suite.total
    assert {(r.task_id, r.agent, r.passed) for r in loaded.records} == {
        (r.task_id, r.agent, r.passed) for r in suite.records
    }
    # The on-disk form is plain JSON.
    assert json.loads(path.read_text(encoding="utf-8"))["totals"]["total"] == suite.total


# --- reports ---------------------------------------------------------------


def test_markdown_report_has_table_and_rows() -> None:
    suite = SC.run_suite(_all_tasks(), agents=("mock", "scripted"), clock=_fixed_clock())
    md = RP.suite_to_markdown(suite)
    assert "| task id | agent | method | result |" in md
    assert "bugfix/sum-range-off-by-one" in md
    assert "fail" in md and "pass" in md
    assert "## Notes" in md


def test_html_report_is_self_contained() -> None:
    suite = SC.run_suite(_all_tasks(), agents=("mock",), clock=_fixed_clock())
    html = RP.suite_to_html(suite)
    assert "<!doctype html>" in html.lower()
    assert "<table>" in html and "bugfix/sum-range-off-by-one" in html
    assert 'class="fail"' in html or 'class="muted"' in html


def test_report_escapes_table_cells() -> None:
    # A failure reason containing a pipe must not break the Markdown table.
    rec = SC.EvalRecord(
        task_id="t/x",
        agent="mock",
        outcome=SC.Outcome.FAILED,
        passed=False,
        runtime_seconds=0.1,
        tool_call_count=0,
        command_count=0,
        blocked_count=0,
        phase_reached="done",
        stop_reason="x",
        failure_reason="a | b\nc",
        score={"method": "test_command"},
    )
    md = RP.suite_to_markdown(SC.SuiteResult(records=(rec,)))
    # The pipe is escaped and the newline collapsed, so the row stays one line.
    assert "a \\| b c" in md


# --- CLI -------------------------------------------------------------------


def test_cli_eval_run_prints_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "run", "--dir", str(TASKS_DIR), "--agent", "mock"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Evaluation results" in out and "| task id |" in out


def test_cli_eval_run_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "run", "--dir", str(TASKS_DIR), "--agent", "mock", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["totals"]["total"] == len(_all_tasks())  # one mock run per task
    assert payload["schema_version"] == SC.SCHEMA_VERSION


def test_cli_eval_run_writes_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = tmp_path / "eval.json"
    report_html = tmp_path / "eval.html"
    rc = cli.main(
        [
            "eval",
            "run",
            "--dir",
            str(TASKS_DIR),
            "--agent",
            "scripted",
            "--out",
            str(out_json),
            "--report",
            str(report_html),
        ]
    )
    assert rc == 0
    assert out_json.is_file() and report_html.is_file()
    assert "<!doctype html>" in report_html.read_text(encoding="utf-8").lower()
    # The written result reloads.
    assert SC.load_suite_result(out_json).total >= 1


def test_cli_eval_report_from_saved_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = tmp_path / "eval.json"
    cli.main(["eval", "run", "--dir", str(TASKS_DIR), "--agent", "mock", "--out", str(out_json)])
    capsys.readouterr()  # drop the run's output
    rc = cli.main(["eval", "report", str(out_json), "--format", "markdown"])
    out = capsys.readouterr().out
    assert rc == 0 and "Evaluation results" in out


def test_cli_eval_report_missing_file_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "report", "/no/such/result.json"])
    assert rc == 1 and "could not load" in capsys.readouterr().err


def test_cli_eval_no_action_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval"])
    assert rc == 0 and "run" in capsys.readouterr().out
