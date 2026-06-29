"""Tests for Milestone 9 — regression comparison and flakiness analysis.

CPU-only and offline. Covers:

- the comparison buckets (improved / regressed / unchanged / flaky / added /
  removed) over hand-built "fake agent versions" — the plan's validation;
- flaky detection, both from repeated records collapsed inside one side of a
  comparison and from :func:`analyze_flakiness` over a sequence of repeats;
- determinism: re-running the real shipped suite N times yields zero flaky keys;
- JSON round-trips for both report types and the Markdown reports;
- the ``eval compare`` / ``eval rerun`` CLI, including exit codes.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from code_agent_runtime import cli
from code_agent_runtime import reports as RP
from code_agent_runtime import scoring as SC
from code_agent_runtime import tasks as TK

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"


def _rec(task_id: str, agent: str, outcome: str, passed: bool | None, *, tc: int = 0) -> SC.EvalRecord:
    """A minimal :class:`EvalRecord` for constructing synthetic suite results."""
    return SC.EvalRecord(
        task_id=task_id,
        agent=agent,
        outcome=outcome,
        passed=passed,
        runtime_seconds=1.0,
        tool_call_count=tc,
        command_count=0,
        blocked_count=0,
        phase_reached="done",
        stop_reason="ok",
        failure_reason=None if passed is not False else "test command failed",
        score={"method": "test_command"},
    )


def _suite(records, *, label=None, skipped=()) -> SC.SuiteResult:
    return SC.SuiteResult(records=tuple(records), skipped=tuple(skipped), label=label)


def _fixed_clock():
    counter = itertools.count()
    return lambda: float(next(counter))


def _all_tasks():
    return list(TK.discover_tasks(TASKS_DIR, resolve_fixture=True))


# --- compare_suites buckets (fake agent versions) --------------------------


def test_compare_buckets_improved_regressed_unchanged() -> None:
    baseline = _suite(
        [
            _rec("t/fixed", "scripted", "failed", False),  # will improve
            _rec("t/broken", "scripted", "passed", True),  # will regress
            _rec("t/stable", "scripted", "passed", True),  # stays passing
            _rec("t/inspect", "scripted", "not_scored", None),  # stays not_scored
        ],
        label="agent-v1",
    )
    candidate = _suite(
        [
            _rec("t/fixed", "scripted", "passed", True),
            _rec("t/broken", "scripted", "failed", False),
            _rec("t/stable", "scripted", "passed", True),
            _rec("t/inspect", "scripted", "not_scored", None),
        ],
        label="agent-v2",
    )
    cmp = SC.compare_suites(baseline, candidate)
    counts = cmp.counts()
    assert counts["improved"] == 1 and counts["regressed"] == 1 and counts["unchanged"] == 2
    assert {(e.task_id) for e in cmp.improved} == {"t/fixed"}
    assert {(e.task_id) for e in cmp.regressed} == {"t/broken"}
    assert cmp.has_regressions is True
    # The transition is recorded in detail for both the improved and regressed keys.
    assert cmp.improved[0].detail == "failed → passed"
    assert cmp.regressed[0].detail == "passed → failed"
    assert cmp.baseline_label == "agent-v1" and cmp.candidate_label == "agent-v2"


def test_compare_added_and_removed_keys() -> None:
    baseline = _suite([_rec("t/old", "mock", "passed", True)])
    candidate = _suite([_rec("t/new", "mock", "failed", False)])
    cmp = SC.compare_suites(baseline, candidate)
    counts = cmp.counts()
    assert counts["added"] == 1 and counts["removed"] == 1
    assert cmp.added[0].task_id == "t/new" and cmp.added[0].candidate_outcome == "failed"
    assert cmp.removed[0].task_id == "t/old" and cmp.removed[0].baseline_outcome == "passed"
    # Neither added nor removed is a regression on its own.
    assert cmp.has_regressions is False


def test_compare_outcome_change_without_pass_change_is_unchanged() -> None:
    # failed -> error: neither gains nor loses a pass, so it stays 'unchanged'
    # but the transition is surfaced in detail (nothing silently dropped).
    baseline = _suite([_rec("t/x", "mock", "failed", False)])
    candidate = _suite([_rec("t/x", "mock", "error", None)])
    cmp = SC.compare_suites(baseline, candidate)
    assert cmp.counts()["unchanged"] == 1 and not cmp.has_regressions
    assert "failed → error" in cmp.unchanged[0].detail


def test_compare_pass_to_error_is_regression() -> None:
    baseline = _suite([_rec("t/x", "mock", "passed", True)])
    candidate = _suite([_rec("t/x", "mock", "error", None)])
    cmp = SC.compare_suites(baseline, candidate)
    assert cmp.counts()["regressed"] == 1 and cmp.has_regressions


def test_compare_flaky_side_is_reported_flaky_not_regressed() -> None:
    # A merged side with disagreeing repeats for one key collapses to 'flaky',
    # which must win over any improved/regressed classification.
    baseline = _suite([_rec("t/x", "mock", "passed", True)])
    flaky_candidate = _suite(
        [_rec("t/x", "mock", "passed", True), _rec("t/x", "mock", "failed", False)]
    )
    cmp = SC.compare_suites(baseline, flaky_candidate)
    assert cmp.counts()["flaky"] == 1
    assert cmp.counts()["regressed"] == 0
    assert cmp.flaky[0].candidate_flaky is True


def test_comparison_json_round_trip(tmp_path: Path) -> None:
    baseline = _suite([_rec("t/a", "mock", "failed", False)], label="v1")
    candidate = _suite([_rec("t/a", "mock", "passed", True)], label="v2")
    cmp = SC.compare_suites(baseline, candidate)
    path = tmp_path / "cmp.json"
    SC.write_comparison(cmp, path)
    loaded = SC.load_comparison(path)
    assert loaded.counts() == cmp.counts()
    assert loaded.baseline_label == "v1" and loaded.candidate_label == "v2"
    assert json.loads(path.read_text(encoding="utf-8"))["counts"]["improved"] == 1


# --- flakiness analysis ----------------------------------------------------


def test_analyze_flakiness_flags_only_flipping_keys() -> None:
    repeats = [
        _suite([_rec("t/stable", "mock", "passed", True), _rec("t/flip", "mock", "passed", True)]),
        _suite([_rec("t/stable", "mock", "passed", True), _rec("t/flip", "mock", "failed", False)]),
        _suite([_rec("t/stable", "mock", "passed", True), _rec("t/flip", "mock", "passed", True)]),
    ]
    report = SC.analyze_flakiness(repeats, label="x")
    assert report.runs == 3
    assert {e.task_id for e in report.flaky} == {"t/flip"}
    assert {e.task_id for e in report.stable} == {"t/stable"}
    flip = report.flaky[0]
    assert flip.runs == 3 and flip.pass_count == 2 and flip.fail_count == 1
    assert pytest.approx(flip.pass_rate) == 2 / 3
    assert flip.distinct_outcomes == ("passed", "failed")
    assert report.has_flakes is True


def test_flakiness_signal_variation_is_not_a_flake() -> None:
    # Same verdict every repeat, but the tool-call count varies: reported as
    # signal_varied, not counted as a flake.
    repeats = [
        _suite([_rec("t/x", "mock", "passed", True, tc=2)]),
        _suite([_rec("t/x", "mock", "passed", True, tc=5)]),
    ]
    report = SC.analyze_flakiness(repeats)
    entry = report.entries[0]
    assert entry.flaky is False and entry.signal_varied is True
    assert report.has_flakes is False


def test_flakiness_json_round_trip(tmp_path: Path) -> None:
    repeats = [
        _suite([_rec("t/x", "mock", "passed", True)]),
        _suite([_rec("t/x", "mock", "failed", False)]),
    ]
    report = SC.analyze_flakiness(repeats, label="rt")
    path = tmp_path / "flaky.json"
    SC.write_flakiness(report, path)
    loaded = SC.load_flakiness(path)
    assert loaded.runs == 2 and loaded.label == "rt"
    assert loaded.counts() == report.counts()


# --- rerun mode + determinism over the real suite --------------------------


def test_run_repeated_real_suite_is_deterministic() -> None:
    tasks = _all_tasks()
    suites = SC.run_repeated(tasks, repeats=2, clock=_fixed_clock())
    assert len(suites) == 2
    report = SC.analyze_flakiness(suites)
    # The deterministic baseline agents never flake, and their effort signals
    # (tool/command counts) are identical across repeats too.
    assert report.flaky == ()
    assert all(not e.signal_varied for e in report.entries)
    assert report.has_flakes is False
    # Every (task, agent) key recorded once per repeat.
    assert all(e.runs == 2 for e in report.entries)


def test_run_repeated_rejects_zero() -> None:
    with pytest.raises(ValueError):
        SC.run_repeated(_all_tasks(), repeats=0)


def test_merge_suites_concatenates_records() -> None:
    s1 = _suite([_rec("t/x", "mock", "passed", True)], skipped=[{"task_id": "t/y", "agent": "probe"}])
    s2 = _suite([_rec("t/x", "mock", "failed", False)])
    merged = SC.merge_suites([s1, s2], label="m")
    assert len(merged.records) == 2 and merged.label == "m"
    assert merged.skipped == s1.skipped  # first input's skipped set is kept
    # A self-comparison of a merged (flaky) result reports the key as flaky.
    cmp = SC.compare_suites(merged, merged)
    assert cmp.counts()["flaky"] == 1


def test_merge_suites_empty_raises() -> None:
    with pytest.raises(ValueError):
        SC.merge_suites([])


# --- reports ---------------------------------------------------------------


def test_regression_markdown_has_sections_and_counts() -> None:
    baseline = _suite(
        [_rec("t/fixed", "mock", "failed", False), _rec("t/broken", "mock", "passed", True)],
        label="v1",
    )
    candidate = _suite(
        [_rec("t/fixed", "mock", "passed", True), _rec("t/broken", "mock", "failed", False)],
        label="v2",
    )
    md = RP.regression_to_markdown(SC.compare_suites(baseline, candidate))
    assert "# Regression comparison" in md
    assert "1 improved, 1 regressed" in md
    assert "## Improved (gained a pass)" in md and "## Regressed (lost a pass)" in md
    assert "t/fixed" in md and "t/broken" in md
    assert "baseline: v1 → candidate: v2" in md


def test_flakiness_markdown_reports_no_flakes_clearly() -> None:
    repeats = [
        _suite([_rec("t/x", "mock", "passed", True)]),
        _suite([_rec("t/x", "mock", "passed", True)]),
    ]
    md = RP.flakiness_to_markdown(SC.analyze_flakiness(repeats))
    assert "# Flakiness analysis" in md
    assert "No flaky keys" in md
    assert "| task id | agent | runs |" in md


def test_regression_report_escapes_pipes() -> None:
    # A label containing a pipe must not break the report's italic line.
    baseline = _suite([_rec("t/a", "mock", "passed", True)], label="a|b")
    candidate = _suite([_rec("t/a", "mock", "passed", True)], label="c|d")
    md = RP.regression_to_markdown(SC.compare_suites(baseline, candidate))
    # The pipe is escaped so the italic baseline/candidate line stays intact.
    assert "a\\|b" in md and "c\\|d" in md


# --- CLI -------------------------------------------------------------------


def _write_suite(path: Path, suite: SC.SuiteResult) -> None:
    SC.write_suite_result(suite, path)


def test_cli_eval_compare_regression_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = tmp_path / "v1.json"
    cand = tmp_path / "v2.json"
    _write_suite(base, _suite([_rec("t/x", "mock", "passed", True)], label="v1"))
    _write_suite(cand, _suite([_rec("t/x", "mock", "failed", False)], label="v2"))
    rc = cli.main(["eval", "compare", str(base), str(cand)])
    out = capsys.readouterr().out
    assert rc == 1  # a regression gates nonzero
    assert "Regression comparison" in out and "1 regressed" in out


def test_cli_eval_compare_no_change_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = _suite([_rec("t/x", "mock", "passed", True)], label="v")
    base = tmp_path / "a.json"
    cand = tmp_path / "b.json"
    _write_suite(base, suite)
    _write_suite(cand, suite)
    rc = cli.main(["eval", "compare", str(base), str(cand), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["counts"]["unchanged"] == 1 and payload["counts"]["regressed"] == 0


def test_cli_eval_compare_writes_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = tmp_path / "v1.json"
    cand = tmp_path / "v2.json"
    _write_suite(base, _suite([_rec("t/x", "mock", "failed", False)], label="v1"))
    _write_suite(cand, _suite([_rec("t/x", "mock", "passed", True)], label="v2"))
    out_json = tmp_path / "cmp.json"
    report_md = tmp_path / "cmp.md"
    rc = cli.main(
        ["eval", "compare", str(base), str(cand), "--out", str(out_json), "--report", str(report_md)]
    )
    assert rc == 0  # an improvement, no regression
    assert out_json.is_file() and report_md.is_file()
    assert SC.load_comparison(out_json).counts()["improved"] == 1
    assert "Improved" in report_md.read_text(encoding="utf-8")


def test_cli_eval_compare_missing_file_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "compare", "/no/such/a.json", "/no/such/b.json"])
    assert rc == 1 and "could not load" in capsys.readouterr().err


def test_cli_eval_rerun_real_suite_no_flakes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "rerun", "--dir", str(TASKS_DIR), "--agent", "scripted", "--repeats", "2"])
    out = capsys.readouterr().out
    assert rc == 0  # deterministic → no flakes
    assert "Flakiness analysis" in out and "No flaky keys" in out


def test_cli_eval_rerun_json_and_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_json = tmp_path / "flaky.json"
    rc = cli.main(
        [
            "eval",
            "rerun",
            "--dir",
            str(TASKS_DIR),
            "--agent",
            "mock",
            "--repeats",
            "2",
            "--out",
            str(out_json),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["runs"] == 2 and payload["counts"]["flaky"] == 0
    assert out_json.is_file()
    assert SC.load_flakiness(out_json).runs == 2


def test_cli_eval_rerun_rejects_zero_repeats(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["eval", "rerun", "--dir", str(TASKS_DIR), "--repeats", "0"])
    assert rc == 1 and "repeats must be >= 1" in capsys.readouterr().err
