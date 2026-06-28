"""Smoke tests for the Milestone 0 scaffold.

These tests are deliberately cheap and CPU-only. They assert that the package
imports, the CLI runs, and the documented project skeleton exists. They do not
make network or paid-API calls.
"""

from __future__ import annotations

import pytest

import code_agent_runtime
from code_agent_runtime import cli


def test_package_exposes_version() -> None:
    assert isinstance(code_agent_runtime.__version__, str)
    # Looks like a dotted version string (e.g. "0.0.0").
    parts = code_agent_runtime.__version__.split(".")
    assert len(parts) >= 2
    assert all(part.isdigit() for part in parts[:2])


def test_package_metadata_present() -> None:
    assert code_agent_runtime.PROJECT_NAME
    assert "runtime" in code_agent_runtime.PROJECT_SUMMARY.lower()


def test_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["version"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == code_agent_runtime.__version__


def test_info_command(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["info"])
    assert rc == 0
    out = capsys.readouterr().out
    assert code_agent_runtime.PROJECT_NAME in out
    assert "Milestone" in out


def test_no_args_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage:" in out.lower()


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse's --help raises SystemExit(0).
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "code-agent-runtime" in out


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert code_agent_runtime.__version__ in out
