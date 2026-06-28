"""Tests for the Milestone 1 environment check.

CPU-only and offline. The check is read-only; these tests assert it produces a
structured, honest report and that the CLI surfaces it correctly.
"""

from __future__ import annotations

import json

import pytest

from code_agent_runtime import cli, environment


def test_report_is_structured_and_passes_on_this_interpreter() -> None:
    report = environment.run_environment_checks()
    assert report.checks, "expected at least one check"
    # The interpreter running the suite is by definition supported.
    py = next(c for c in report.checks if c.name == "python_version")
    assert py.required is True
    assert py.ok is True
    # Overall result is governed solely by required checks.
    assert report.ok is True


def test_min_python_is_required_and_enforced() -> None:
    py = next(c for c in environment.run_environment_checks().checks if c.name == "python_version")
    assert environment.MIN_PYTHON == (3, 10)
    assert "3." in py.detail


def test_format_report_mentions_result_and_checks() -> None:
    text = environment.format_report(environment.run_environment_checks())
    assert "Environment check" in text
    assert "python_version" in text
    assert "Result: PASS" in text


def test_env_check_main_text(capsys: pytest.CaptureFixture[str]) -> None:
    rc = environment.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Result: PASS" in out


def test_env_check_main_json_is_parseable(capsys: pytest.CaptureFixture[str]) -> None:
    rc = environment.main(["--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    names = {c["name"] for c in payload["checks"]}
    assert {"python_version", "platform", "git"} <= names


def test_cli_env_check_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["env-check"])
    assert rc == 0
    assert "Environment check" in capsys.readouterr().out
