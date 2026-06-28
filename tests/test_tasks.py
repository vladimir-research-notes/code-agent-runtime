"""Tests for the Milestone 2 versioned task format.

CPU-only and offline. Covers schema validation (valid and invalid documents),
JSON/optional-YAML loading, fixture resolution, task discovery over the
repository's real ``tasks/`` tree, and the ``tasks list`` / ``tasks show`` CLI
subcommands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_agent_runtime import cli
from code_agent_runtime import tasks as T

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"

EXPECTED_TASK_IDS = {
    "bugfix/sum-range-off-by-one",
    "cli/add-shout-flag",
    "security/unsafe-command-demo",
}


def _valid_task_dict(**overrides) -> dict:
    base = {
        "version": 1,
        "id": "bugfix/example",
        "title": "Example task",
        "prompt": "Fix the thing so the tests pass.",
        "fixture": "examples/tiny_python_bug",
        "scoring_method": "test_command",
        "test_command": "python3 -m pytest -q",
        "allowed_tools": ["read_file", "run_tests"],
    }
    base.update(overrides)
    return base


# --- schema validation -----------------------------------------------------


def test_valid_dict_builds_task() -> None:
    task = T.validate_task_dict(_valid_task_dict(), source="mem")
    assert task.id == "bugfix/example"
    assert task.test_command == ("python3", "-m", "pytest", "-q")
    assert task.test_command_str == "python3 -m pytest -q"
    assert task.timeout_seconds == T.DEFAULT_TIMEOUT_SECONDS
    assert task.allowed_tools == ("read_file", "run_tests")
    assert task.resource_limits.network is False
    assert task.source_path == "mem"


def test_test_command_accepts_argv_list() -> None:
    task = T.validate_task_dict(
        _valid_task_dict(test_command=["python3", "-m", "pytest"]), source="mem"
    )
    assert task.test_command == ("python3", "-m", "pytest")


def test_to_dict_round_trips_through_validation() -> None:
    task = T.validate_task_dict(_valid_task_dict(), source="mem")
    payload = task.to_dict()
    # A re-validated copy (sans loader-only source_path) is equivalent.
    payload.pop("source_path")
    again = T.validate_task_dict(payload, source="mem2")
    assert again.to_dict()["id"] == task.to_dict()["id"]
    assert again.test_command == task.test_command
    assert json.dumps(payload)  # serialisable


def test_unknown_top_level_field_is_error() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(_valid_task_dict(oops=1), source="bad")
    assert any("unknown field" in p for p in exc.value.problems)


def test_missing_required_fields_collects_all_problems() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict({"version": 1}, source="bad")
    problems = exc.value.problems
    for field in ("id", "title", "prompt", "fixture", "scoring_method"):
        assert any(f"'{field}'" in p for p in problems), field
    # The rendered message names the source and is multi-line/readable.
    text = str(exc.value)
    assert "bad" in text
    assert text.count("\n") >= len(problems)


def test_bad_id_shape_is_rejected() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(_valid_task_dict(id="Bad ID!"), source="bad")
    assert any("'id'" in p for p in exc.value.problems)


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(_valid_task_dict(allowed_tools=["read-file"]), source="bad")
    assert any("unknown tool" in p for p in exc.value.problems)


def test_unknown_scoring_method_is_rejected() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(_valid_task_dict(scoring_method="magic"), source="bad")
    assert any("scoring_method" in p for p in exc.value.problems)


def test_unsupported_version_is_rejected() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(_valid_task_dict(version=999), source="bad")
    assert any("version" in p for p in exc.value.problems)


def test_test_command_required_when_scoring_by_command() -> None:
    payload = _valid_task_dict()
    del payload["test_command"]
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(payload, source="bad")
    assert any("requires a non-empty 'test_command'" in p for p in exc.value.problems)


def test_scoring_none_needs_no_test_command() -> None:
    payload = _valid_task_dict(scoring_method="none")
    del payload["test_command"]
    task = T.validate_task_dict(payload, source="mem")
    assert task.test_command is None


def test_bad_timeout_and_limits_are_rejected() -> None:
    with pytest.raises(T.TaskValidationError) as exc:
        T.validate_task_dict(
            _valid_task_dict(timeout_seconds=-5, resource_limits={"memory_mb": 0, "bogus": 1}),
            source="bad",
        )
    problems = exc.value.problems
    assert any("timeout_seconds" in p for p in problems)
    assert any("resource_limits.memory_mb" in p for p in problems)
    assert any("unknown key" in p for p in problems)


def test_non_mapping_document_is_rejected() -> None:
    with pytest.raises(T.TaskValidationError):
        T.validate_task_dict([1, 2, 3], source="bad")


# --- loading from disk -----------------------------------------------------


def test_load_task_json_from_disk(tmp_path: Path) -> None:
    (tmp_path / "fix").mkdir()
    task_file = tmp_path / "demo.task.json"
    task_file.write_text(json.dumps(_valid_task_dict(fixture="fix")), encoding="utf-8")
    task = T.load_task(task_file)
    assert task.id == "bugfix/example"
    assert task.source_path == str(task_file)


def test_load_task_reports_json_syntax_error(tmp_path: Path) -> None:
    task_file = tmp_path / "broken.task.json"
    task_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(T.TaskValidationError) as exc:
        T.load_task(task_file)
    assert any("invalid JSON" in p for p in exc.value.problems)


def test_load_task_unrecognised_filename(tmp_path: Path) -> None:
    task_file = tmp_path / "demo.json"  # missing the .task. marker
    task_file.write_text("{}", encoding="utf-8")
    with pytest.raises(T.TaskValidationError) as exc:
        T.load_task(task_file)
    assert any("unrecognised task filename" in p for p in exc.value.problems)


def test_missing_fixture_is_error_when_resolved(tmp_path: Path) -> None:
    task_file = tmp_path / "demo.task.json"
    task_file.write_text(
        json.dumps(_valid_task_dict(fixture="does-not-exist")), encoding="utf-8"
    )
    with pytest.raises(T.TaskValidationError) as exc:
        T.load_task(task_file, resolve_fixture=True)
    assert any("fixture path does not exist" in p for p in exc.value.problems)
    # Schema-only load still succeeds.
    assert T.load_task(task_file, resolve_fixture=False).id == "bugfix/example"


def test_yaml_loading_when_available(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    import yaml

    (tmp_path / "fix").mkdir()
    task_file = tmp_path / "demo.task.yaml"
    task_file.write_text(yaml.safe_dump(_valid_task_dict(fixture="fix")), encoding="utf-8")
    task = T.load_task(task_file)
    assert task.id == "bugfix/example"


# --- discovery over the real repo -----------------------------------------


def test_discover_real_tasks_load_and_resolve() -> None:
    tasks = T.discover_tasks(TASKS_DIR, resolve_fixture=True)
    ids = {t.id for t in tasks}
    assert EXPECTED_TASK_IDS <= ids
    # Every shipped task points at a fixture that exists on disk.
    for task in tasks:
        assert T.fixture_exists(task), f"{task.id} fixture missing"


def test_find_task_by_id_and_path() -> None:
    by_id = T.find_task(TASKS_DIR, "bugfix/sum-range-off-by-one")
    assert by_id.scoring_method == "test_command"
    by_path = T.find_task(TASKS_DIR, str(by_id.source_path))
    assert by_path.id == by_id.id


def test_find_task_unknown_id_raises() -> None:
    with pytest.raises(T.TaskValidationError):
        T.find_task(TASKS_DIR, "no/such-task")


# --- CLI -------------------------------------------------------------------


def test_cli_tasks_list(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks", "list", "--dir", str(TASKS_DIR)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "bugfix/sum-range-off-by-one" in out
    assert "fixture: ok" in out


def test_cli_tasks_list_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks", "list", "--dir", str(TASKS_DIR), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["count"] >= len(EXPECTED_TASK_IDS)
    assert payload["errors"] == []
    assert EXPECTED_TASK_IDS <= {t["id"] for t in payload["tasks"]}


def test_cli_tasks_show(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks", "show", "cli/add-shout-flag", "--dir", str(TASKS_DIR)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Task: cli/add-shout-flag" in out
    assert "test command  : python3 -m pytest -q" in out


def test_cli_tasks_show_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks", "show", "security/unsafe-command-demo", "--dir", str(TASKS_DIR), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["id"] == "security/unsafe-command-demo"
    assert payload["scoring_method"] == "none"
    assert payload["test_command"] is None


def test_cli_tasks_show_unknown_returns_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks", "show", "no/such-task", "--dir", str(TASKS_DIR)])
    assert rc == 1
    assert "no task found" in capsys.readouterr().err


def test_cli_tasks_no_action_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tasks"])
    assert rc == 0
    assert "list" in capsys.readouterr().out
