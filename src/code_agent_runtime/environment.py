"""Environment check for Code Agent Runtime (Milestone 1).

Reports whether the host can build, test, and (later) run the runtime under the
project's CPU-only, no-paid-API policy. The check is intentionally read-only and
side-effect free: it inspects the interpreter, looks for optional tooling on
``PATH``, and asks ``git`` whether the current directory is a work tree. It never
touches the network and never requires an API key.

The module is usable three ways:

- as a library: :func:`run_environment_checks` returns structured results;
- via the CLI: ``code-agent-runtime env-check`` (see :mod:`code_agent_runtime.cli`);
- as a script: ``python3 scripts/00_check_environment.py``.

Exit status is ``0`` when every *required* check passes and ``1`` otherwise, so
the check can gate later steps in a pipeline.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass

#: Minimum Python version, kept in sync with ``pyproject.toml`` ``requires-python``.
MIN_PYTHON = (3, 10)


@dataclass(frozen=True)
class Check:
    """A single environment check result.

    ``required`` checks gate the overall result; non-required checks are advisory
    (they surface recommendations without failing the run).
    """

    name: str
    ok: bool
    required: bool
    detail: str


@dataclass(frozen=True)
class EnvironmentReport:
    """Aggregate of all environment checks."""

    checks: list[Check]

    @property
    def ok(self) -> bool:
        """True when every *required* check passed."""
        return all(check.ok for check in self.checks if check.required)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": [asdict(c) for c in self.checks]}


def _python_version_check() -> Check:
    info = sys.version_info
    current = f"{info.major}.{info.minor}.{info.micro}"
    ok = (info.major, info.minor) >= MIN_PYTHON
    want = ".".join(str(part) for part in MIN_PYTHON)
    detail = f"Python {current} (require >= {want})"
    return Check(name="python_version", ok=ok, required=True, detail=detail)


def _tool_check(name: str, executable: str, *, why: str) -> Check:
    """Check for an optional command-line tool on ``PATH``."""
    path = shutil.which(executable)
    if path:
        detail = f"{executable} found at {path}"
    else:
        detail = f"{executable} not found on PATH ({why})"
    # Optional: missing tooling is a recommendation, not a hard failure.
    return Check(name=name, ok=path is not None, required=False, detail=detail)


def _module_check(name: str, module: str, *, why: str) -> Check:
    """Check whether a Python module is importable without importing it."""
    import importlib.util

    spec = importlib.util.find_spec(module)
    detail = f"{module} importable" if spec else f"{module} not importable ({why})"
    return Check(name=name, ok=spec is not None, required=False, detail=detail)


def _git_worktree_check() -> Check:
    """Report whether the current directory is inside a git work tree."""
    if shutil.which("git") is None:
        return Check(
            name="git_worktree",
            ok=False,
            required=False,
            detail="git not available; hygiene scan falls back to a filesystem walk",
        )
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - defensive
        return Check(name="git_worktree", ok=False, required=False, detail=f"git error: {exc}")
    inside = result.returncode == 0 and result.stdout.strip() == "true"
    detail = (
        "inside a git work tree (hygiene scans tracked files)"
        if inside
        else "not a git work tree (hygiene falls back to a filesystem walk)"
    )
    return Check(name="git_worktree", ok=inside, required=False, detail=detail)


def _platform_check() -> Check:
    detail = f"{platform.system()} {platform.release()} ({platform.machine()})"
    return Check(name="platform", ok=True, required=False, detail=detail)


def _offline_policy_check() -> Check:
    # Informational: states the project policy. Always "ok" because the default
    # path genuinely requires no network or paid API.
    return Check(
        name="offline_friendly",
        ok=True,
        required=False,
        detail="default tests and tooling need no network or paid API",
    )


def run_environment_checks() -> EnvironmentReport:
    """Run all environment checks and return a structured report."""
    checks = [
        _python_version_check(),
        _platform_check(),
        _tool_check("git", "git", why="needed for tracked-file hygiene scans and later milestones"),
        _module_check("pytest", "pytest", why="needed to run the test suite"),
        _git_worktree_check(),
        _offline_policy_check(),
    ]
    return EnvironmentReport(checks=checks)


def _marker(check: Check) -> str:
    if check.ok:
        return "ok"
    return "FAIL" if check.required else "warn"


def format_report(report: EnvironmentReport) -> str:
    """Render a report as aligned, human-readable text."""
    width = max((len(c.name) for c in report.checks), default=0)
    lines = ["Environment check — Code Agent Runtime", ""]
    for check in report.checks:
        tag = "required" if check.required else "optional"
        lines.append(f"  [{_marker(check):>4}] {check.name:<{width}}  {check.detail}  ({tag})")
    lines.append("")
    lines.append("Result: PASS" if report.ok else "Result: FAIL (a required check did not pass)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the CLI subcommand and the ``scripts/`` wrapper.

    Returns ``0`` when all required checks pass, ``1`` otherwise.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="code-agent-runtime env-check",
        description="Check that the host satisfies the runtime's CPU-only, no-paid-API requirements.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args(argv)

    report = run_environment_checks()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - exercised via scripts/ and __main__
    raise SystemExit(main())
