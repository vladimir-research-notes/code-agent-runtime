"""Tests for the Milestone 12 reproducible case study.

CPU-only and offline. Covers:

- the expanded task suite (10–20 tasks spanning every plan category), and that
  each case-study task either has a scripted solution or a sandbox probe so it is
  actually attempted, not skipped;
- the discriminating outcome the case study rests on — the ``mock`` null baseline
  fails the tasks that require a change while the ``scripted`` solver passes them;
- the second sandbox probe (``security/secret-read-demo``) blocking every
  credential-exfiltration action while allowing the benign in-workspace read;
- the CSV report exporter (header, runtime toggle, JSON-round-trip parity), the
  committed canonical CSV staying in sync with a freshly generated one, and the
  ``eval`` CLI emitting CSV;
- the case-study runner script writing its result/CSV/report/trace artifacts.

Assertions that depend on the captured git diff (the ``diff_constraint`` /
``custom`` scoped runs) are gated on ``git`` being present.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from code_agent_runtime import agents as A
from code_agent_runtime import cli
from code_agent_runtime import reports as RP
from code_agent_runtime import runtime as R
from code_agent_runtime import scoring as SC
from code_agent_runtime import tasks as TK

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
CANONICAL_CSV = REPO_ROOT / "docs" / "results" / "case_study.csv"
SECRET_DEMO = "security/secret-read-demo"
HAS_GIT = shutil.which("git") is not None

#: Tasks added in Milestone 12, with the expected (mock, scripted) verdicts.
NEW_SOLVABLE_TASKS = (
    "bugfix/temp-convert-ratio",
    "bugfix/gcd-modulo-swap",
    "refactor/extract-rate-constant",
    "cli/add-reverse-flag",
    "tests/implement-slugify",
    "tests/implement-kv-parser",
)
#: New tasks whose scripted verdict depends on the captured git diff.
_GIT_GATED = {"refactor/extract-rate-constant"}


def _all_tasks():
    return list(TK.discover_tasks(TASKS_DIR, resolve_fixture=True))


# --- the suite shape -------------------------------------------------------


def test_suite_has_case_study_breadth() -> None:
    tasks = _all_tasks()
    assert 10 <= len(tasks) <= 20, f"case study should have 10–20 tasks, found {len(tasks)}"
    categories = {t.metadata.get("category") for t in tasks}
    # Every plan category is represented.
    assert {"bugfix", "refactor", "cli_change", "tests_must_pass", "security"} <= categories


def test_every_task_is_attempted_by_some_agent() -> None:
    """No case-study task is a dead end: each has a scripted solution or a probe."""
    for task in _all_tasks():
        attempted = A.has_solution(task.id) or A.has_probe(task.id)
        assert attempted, f"task {task.id} has neither a scripted solution nor a probe"


# --- the discriminating result --------------------------------------------


def test_new_tasks_mock_fails_scripted_passes() -> None:
    tasks = [TK.find_task(TASKS_DIR, i) for i in NEW_SOLVABLE_TASKS]
    suite = SC.run_suite(tasks, agents=("mock", "scripted"))
    by_key = {(r.task_id, r.agent): r for r in suite.records}
    for task_id in NEW_SOLVABLE_TASKS:
        assert by_key[(task_id, "mock")].passed is False, task_id
        if task_id in _GIT_GATED and not HAS_GIT:
            continue
        assert by_key[(task_id, "scripted")].passed is True, task_id


def test_new_scripted_solutions_genuinely_pass_via_runtime() -> None:
    """Each new solvable task's scripted plan drives a real run to PASSED."""
    for task_id in NEW_SOLVABLE_TASKS:
        if task_id in _GIT_GATED and not HAS_GIT:
            continue
        task = TK.find_task(TASKS_DIR, task_id)
        result = R.run_task(task, A.build_scripted_agent(task))
        assert result.outcome == R.RunOutcome.PASSED, (task_id, result.score)


# --- the second sandbox probe ----------------------------------------------


def test_secret_read_probe_blocks_exfiltration_and_allows_benign_read() -> None:
    task = TK.find_task(TASKS_DIR, SECRET_DEMO)
    result = R.run_task(task, A.build_unsafe_probe_agent(task))

    assert result.outcome == R.RunOutcome.NOT_SCORED and result.error is None
    tool_steps = [s for s in result.steps if s.action_kind == "tool"]

    benign = tool_steps[0]  # read service.py
    assert benign.tool == "read_file" and benign.allowed and benign.result.ok

    expected_rules = {
        1: "denied_path",        # read .env
        2: "denied_path",        # read .ssh/id_rsa
        3: "denied_path",        # read deploy/prod.pem
        4: "outside_workspace",  # read /etc/passwd
        5: "network_denied",     # scp .env user@host
        6: "network_denied",     # curl ... upload
    }
    for index, rule in expected_rules.items():
        step = tool_steps[index]
        assert not step.allowed, (index, step.tool)
        assert step.result.category == "blocked"
        assert step.result.data["policy_rule"] == rule, (index, step.result.data)

    # No exec-category command ran (all blocked before dispatch).
    assert result.command_count == 0


def test_has_probe_for_both_security_demos() -> None:
    assert A.has_probe(SECRET_DEMO)
    assert A.has_probe("security/unsafe-command-demo")
    assert not A.has_solution(SECRET_DEMO)  # a probe is never a solution


# --- the CSV exporter ------------------------------------------------------


def test_suite_to_csv_header_and_rows() -> None:
    suite = SC.run_suite(_all_tasks(), agents=("mock",))
    csv = RP.suite_to_csv(suite)
    lines = csv.strip().splitlines()
    header = lines[0]
    assert header.startswith("task_id,agent,scoring_method,verdict,runtime_seconds,")
    assert "bugfix/sum-range-off-by-one" in csv
    # One header + one row per record.
    assert len(lines) == 1 + len(suite.records)


def test_suite_to_csv_runtime_toggle_is_deterministic() -> None:
    suite = SC.run_suite(_all_tasks(), agents=("mock",))
    deterministic = RP.suite_to_csv(suite, include_runtime=False)
    assert "runtime_seconds" not in deterministic
    # Two renders without runtime are byte-identical (no wall-clock leak).
    assert deterministic == RP.suite_to_csv(suite, include_runtime=False)


def test_csv_field_with_comma_is_quoted() -> None:
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
        stop_reason="s",
        failure_reason="a, b, c",
        score={"method": "test_command"},
    )
    csv = RP.suite_to_csv(SC.SuiteResult(records=(rec,)), include_runtime=False)
    assert '"a, b, c"' in csv  # the comma-bearing cell is quoted, row stays intact


@pytest.mark.skipif(not HAS_GIT, reason="git not installed (scoped diff verdicts differ)")
def test_committed_canonical_csv_is_in_sync() -> None:
    """The committed deterministic CSV matches a freshly generated one."""
    assert CANONICAL_CSV.is_file(), "docs/results/case_study.csv is missing"
    suite = SC.run_suite(_all_tasks())  # default matrix: mock, scripted, probe
    fresh = RP.suite_to_csv(suite, include_runtime=False)
    committed = CANONICAL_CSV.read_text(encoding="utf-8")
    assert committed == fresh, (
        "docs/results/case_study.csv is stale — regenerate with "
        "`python3 scripts/07_case_study.py --canonical-csv docs/results/case_study.csv`"
    )


# --- CLI -------------------------------------------------------------------


def test_cli_eval_run_writes_csv_report(tmp_path: Path) -> None:
    report_csv = tmp_path / "case.csv"
    rc = cli.main(
        ["eval", "run", "--dir", str(TASKS_DIR), "--agent", "mock", "--report", str(report_csv)]
    )
    assert rc == 0 and report_csv.is_file()
    text = report_csv.read_text(encoding="utf-8")
    assert text.startswith("task_id,agent,scoring_method,")


def test_cli_eval_report_csv_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_json = tmp_path / "eval.json"
    cli.main(["eval", "run", "--dir", str(TASKS_DIR), "--agent", "mock", "--out", str(out_json)])
    capsys.readouterr()  # drop the run's stdout
    rc = cli.main(["eval", "report", str(out_json), "--format", "csv"])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("task_id,agent,scoring_method,")


# --- the runner script -----------------------------------------------------


def test_case_study_script_writes_artifacts(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "case_study_script", REPO_ROOT / "scripts" / "07_case_study.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rc = module.main(["--dir", str(TASKS_DIR), "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "raw" / "case_study.json").is_file()
    assert (tmp_path / "reports" / "case_study.csv").is_file()
    assert (tmp_path / "reports" / "case_study.md").is_file()
    assert (tmp_path / "reports" / "case_study.html").is_file()
    # One trace per attempted run is written and is reloadable.
    traces = list((tmp_path / "traces" / "case_study").glob("*.trace.json"))
    assert len(traces) >= 10
    # The written suite result reloads with all records.
    suite = SC.load_suite_result(tmp_path / "raw" / "case_study.json")
    assert suite.total == len(traces)
