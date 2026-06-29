"""Tests for the Milestone 8 scoring layer.

CPU-only and offline. Unit-tests each scorer against synthetic evidence (a test
result, a captured diff, a workspace directory) so a verdict is checked without
re-running anything: the ``test_command`` scorer, the ``expected_files`` scorer
(present/absent/contains, escaping paths, missing workspace), the
``diff_constraint`` scorer (scope, empty-change, forbidden, max_files, bytecode
noise, no-diff), the ``custom`` registry/hook, and the :func:`score_run`
dispatcher. Also covers the ``scoring_config`` schema validation added for these
methods, and the drift guard that the scoring vocabulary equals the runtime's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_agent_runtime.runtime import RunOutcome
from code_agent_runtime.scoring import (
    CUSTOM_SCORERS,
    Outcome,
    ScoreInput,
    available_custom_scorers,
    changed_paths,
    matches_any,
    register_custom_scorer,
    score_custom,
    score_diff_constraint,
    score_expected_files,
    score_run,
    score_test_command,
)
from code_agent_runtime.tasks import TaskValidationError, validate_task_dict


def _task(scoring_method: str, scoring_config=None, **extra):
    data = {
        "version": 1,
        "id": "t/x",
        "title": "t",
        "prompt": "p",
        "fixture": "examples/tiny_python_bug",
        "scoring_method": scoring_method,
    }
    if scoring_config is not None:
        data["scoring_config"] = scoring_config
    data.update(extra)
    return validate_task_dict(data, source="mem")


def _diff(*paths: str, untracked=()):
    return {
        "files": [{"path": p, "insertions": 1, "deletions": 0, "binary": False} for p in paths],
        "untracked": list(untracked),
        "insertions": len(paths),
        "deletions": 0,
    }


# --- vocabulary drift guard ------------------------------------------------


def test_outcome_vocabulary_matches_runtime() -> None:
    # scoring.Outcome mirrors runtime.RunOutcome; if these drift, the runtime
    # would store a score the report/replay code cannot interpret.
    assert Outcome.ALL == RunOutcome.ALL
    for name in ("PASSED", "FAILED", "NOT_SCORED", "ERROR"):
        assert getattr(Outcome, name) == getattr(RunOutcome, name)


# --- test_command scorer ---------------------------------------------------


def test_test_command_pass_fail_and_missing() -> None:
    task = _task("test_command", test_command="python3 -m pytest -q")
    assert score_test_command(ScoreInput(task, tests={"passed": True, "exit_code": 0})).passed is True
    v = score_test_command(ScoreInput(task, tests={"passed": False, "exit_code": 1}))
    assert v.passed is False and v.outcome == Outcome.FAILED
    # No test result at all is a failure, not a crash.
    assert score_test_command(ScoreInput(task, tests=None)).passed is False


def test_test_command_timeout_fails() -> None:
    task = _task("test_command", test_command="python3 -m pytest -q")
    v = score_test_command(ScoreInput(task, tests={"passed": False, "timed_out": True}))
    assert v.passed is False and "timed out" in v.detail


# --- expected_files scorer -------------------------------------------------


def test_expected_files_present_absent_contains(tmp_path: Path) -> None:
    (tmp_path / "made.py").write_text("answer = 42\n", encoding="utf-8")
    task = _task(
        "expected_files",
        {
            "present": ["made.py"],
            "absent": ["gone.py"],
            "contains": [{"path": "made.py", "text": "answer = 42"}],
        },
    )
    v = score_expected_files(ScoreInput(task, workspace=tmp_path))
    assert v.passed is True and v.outcome == Outcome.PASSED
    assert len(v.checks) == 3 and all(c.passed for c in v.checks)


def test_expected_files_reports_each_failure(tmp_path: Path) -> None:
    (tmp_path / "made.py").write_text("nope\n", encoding="utf-8")
    task = _task(
        "expected_files",
        {"present": ["missing.py"], "contains": [{"path": "made.py", "text": "answer"}]},
    )
    v = score_expected_files(ScoreInput(task, workspace=tmp_path))
    assert v.passed is False
    assert any("missing.py" in c.detail and not c.passed for c in v.checks)
    assert any("answer" in c.detail and not c.passed for c in v.checks)


def test_expected_files_contains_accepts_list(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("alpha beta\n", encoding="utf-8")
    task = _task("expected_files", {"contains": [{"path": "f.py", "text": ["alpha", "beta"]}]})
    assert score_expected_files(ScoreInput(task, workspace=tmp_path)).passed is True
    task2 = _task("expected_files", {"contains": [{"path": "f.py", "text": ["alpha", "missing"]}]})
    assert score_expected_files(ScoreInput(task2, workspace=tmp_path)).passed is False


def test_expected_files_escaping_path_fails(tmp_path: Path) -> None:
    task = _task("expected_files", {"present": ["../escape.txt"]})
    v = score_expected_files(ScoreInput(task, workspace=tmp_path))
    assert v.passed is False and "escapes" in v.checks[0].detail


def test_expected_files_without_workspace_is_not_scored() -> None:
    task = _task("expected_files", {"present": ["x"]})
    v = score_expected_files(ScoreInput(task, workspace=None))
    assert v.outcome == Outcome.NOT_SCORED and v.passed is None


# --- diff_constraint scorer ------------------------------------------------


def test_diff_constraint_within_scope_passes() -> None:
    task = _task("diff_constraint", {"allowed_paths": ["summation.py"]})
    v = score_diff_constraint(ScoreInput(task, diff=_diff("summation.py")))
    assert v.passed is True and v.extra["changed"] == ["summation.py"]


def test_diff_constraint_out_of_scope_fails() -> None:
    task = _task("diff_constraint", {"allowed_paths": ["summation.py"]})
    v = score_diff_constraint(ScoreInput(task, diff=_diff("summation.py", "other.py")))
    assert v.passed is False and "other.py" in v.detail


def test_diff_constraint_empty_change_fails_unless_allowed() -> None:
    task = _task("diff_constraint", {"allowed_paths": ["*.py"]})
    assert score_diff_constraint(ScoreInput(task, diff=_diff())).passed is False
    task2 = _task("diff_constraint", {"allowed_paths": ["*.py"], "allow_empty": True})
    assert score_diff_constraint(ScoreInput(task2, diff=_diff())).passed is True


def test_diff_constraint_max_files_and_forbidden() -> None:
    task = _task(
        "diff_constraint",
        {"allowed_paths": ["*.py"], "max_files": 1},
    )
    assert score_diff_constraint(ScoreInput(task, diff=_diff("a.py", "b.py"))).passed is False
    task2 = _task("diff_constraint", {"allowed_paths": ["*.py"], "forbidden_paths": ["secret.py"]})
    v = score_diff_constraint(ScoreInput(task2, diff=_diff("a.py", "secret.py")))
    assert v.passed is False and "forbidden" in v.detail.lower()


def test_diff_constraint_ignores_bytecode_noise() -> None:
    task = _task("diff_constraint", {"allowed_paths": ["greet.py"]})
    diff = _diff("greet.py", untracked=["__pycache__/greet.cpython-312.pyc"])
    v = score_diff_constraint(ScoreInput(task, diff=diff))
    assert v.passed is True and v.extra["changed"] == ["greet.py"]


def test_diff_constraint_without_diff_is_not_scored() -> None:
    task = _task("diff_constraint", {"allowed_paths": ["*.py"]})
    v = score_diff_constraint(ScoreInput(task, diff=None))
    assert v.outcome == Outcome.NOT_SCORED


def test_changed_paths_and_matches_any() -> None:
    assert matches_any("src/a.py", ["*.py"]) is True
    assert matches_any("src/a.py", ["a.py"]) is True  # basename match
    assert matches_any("src/a.py", ["b.py"]) is False
    assert changed_paths(_diff("a.py", untracked=["a.pyc"])) == ["a.py"]


# --- custom scorer + registry ----------------------------------------------


def test_custom_composite_pass_and_fail() -> None:
    task = _task(
        "custom",
        {"name": "tests_pass_and_diff_scope", "allowed_paths": ["greet.py"]},
        test_command="python3 -m pytest -q",
    )
    ok = score_custom(ScoreInput(task, tests={"passed": True}, diff=_diff("greet.py")))
    assert ok.passed is True and ok.method == "custom"
    # Tests pass but the change strayed out of scope → fail.
    out = score_custom(ScoreInput(task, tests={"passed": True}, diff=_diff("greet.py", "x.py")))
    assert out.passed is False


def test_custom_unknown_scorer_errors() -> None:
    task = _task("custom", {"name": "does-not-exist"})
    v = score_custom(ScoreInput(task))
    assert v.outcome == Outcome.ERROR and "does-not-exist" in v.detail


def test_register_custom_scorer_hook() -> None:
    from code_agent_runtime.scoring.scorer import passed as _passed

    register_custom_scorer("always_pass_demo", lambda inp: _passed("custom", "demo"))
    try:
        assert "always_pass_demo" in available_custom_scorers()
        task = _task("custom", {"name": "always_pass_demo"})
        assert score_custom(ScoreInput(task)).passed is True
    finally:
        CUSTOM_SCORERS.pop("always_pass_demo", None)


def test_register_custom_scorer_rejects_bad_args() -> None:
    with pytest.raises(ValueError):
        register_custom_scorer("", lambda inp: None)
    with pytest.raises(TypeError):
        register_custom_scorer("x", "not callable")


# --- dispatcher + serialisation --------------------------------------------


def test_score_run_dispatches_by_method() -> None:
    none_task = _task("none")
    assert score_run(none_task).outcome == Outcome.NOT_SCORED
    tc = _task("test_command", test_command="python3 -m pytest -q")
    assert score_run(tc, tests={"passed": True}).passed is True


def test_verdict_to_dict_shape() -> None:
    task = _task("expected_files", {"present": ["x"]})
    d = score_run(task, workspace=None).to_dict()
    assert set(d) >= {"method", "outcome", "passed", "detail"}
    # A scored verdict with checks serialises them as plain dicts.
    tmp = score_diff_constraint(ScoreInput(_task("diff_constraint", {"allowed_paths": ["a.py"]}), diff=_diff("a.py")))
    td = tmp.to_dict()
    assert "checks" in td and isinstance(td["checks"], list)


# --- scoring_config schema validation --------------------------------------


def test_schema_accepts_valid_scoring_configs() -> None:
    _task("expected_files", {"present": ["a.py"], "contains": [{"path": "a.py", "text": "x"}]})
    _task("diff_constraint", {"allowed_paths": ["a.py"], "max_files": 2, "allow_empty": False})
    _task("custom", {"name": "tests_pass_and_diff_scope", "allowed_paths": ["a.py"]})


def test_schema_rejects_expected_files_without_expectations() -> None:
    with pytest.raises(TaskValidationError) as exc:
        _task("expected_files", {})
    assert any("expected_files" in p for p in exc.value.problems)


def test_schema_rejects_unknown_scoring_config_key() -> None:
    with pytest.raises(TaskValidationError) as exc:
        _task("diff_constraint", {"allowed_paths": ["a.py"], "bogus": 1})
    assert any("unknown key" in p for p in exc.value.problems)


def test_schema_rejects_diff_constraint_without_allowed_paths() -> None:
    with pytest.raises(TaskValidationError) as exc:
        _task("diff_constraint", {})
    assert any("allowed_paths" in p for p in exc.value.problems)


def test_schema_rejects_custom_without_name() -> None:
    with pytest.raises(TaskValidationError) as exc:
        _task("custom", {})
    assert any("custom" in p and "name" in p for p in exc.value.problems)


def test_schema_rejects_bad_contains() -> None:
    with pytest.raises(TaskValidationError) as exc:
        _task("expected_files", {"contains": [{"path": "a.py"}]})  # no text
    assert any("contains" in p for p in exc.value.problems)
