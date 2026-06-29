"""``run_tests`` — run a task's test command and report pass/fail (Milestone 3).

A thin specialisation of ``run_shell`` aimed at the test-command scoring method
(Milestone 8). It adds one thing the scorer cares about: a ``passed`` boolean
derived from a zero exit code. The default command is ``python3 -m pytest -q``,
matching the project's CPU-only, no-paid-API test convention.
"""

from __future__ import annotations

from typing import Any

from ._exec import normalize_argv, run_command
from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult

#: Default test command when a task/caller does not supply one.
DEFAULT_TEST_COMMAND: tuple[str, ...] = ("python3", "-m", "pytest", "-q")


class RunTestsTool(Tool):
    """Run the test command in the workspace; ``passed`` iff it exits zero."""

    name = "run_tests"
    category = "exec"
    summary = "Run a test command in the workspace and report pass/fail."
    params = (
        ToolParam(
            "command",
            "str|list",
            required=False,
            description="Test command (string or argv); defaults to `python3 -m pytest -q`.",
        ),
        ToolParam(
            "timeout_seconds",
            "int",
            required=False,
            description="Override the context's wall-clock budget for the test run.",
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        command = args.get("command")
        argv = normalize_argv(command) if command is not None else DEFAULT_TEST_COMMAND
        timeout = args.get("timeout_seconds", ctx.timeout_seconds)
        if timeout <= 0:
            raise ToolError("'timeout_seconds' must be a positive integer")

        completed = run_command(
            argv,
            cwd=ctx.workspace,
            timeout_seconds=timeout,
            max_output_bytes=ctx.max_output_bytes,
        )
        passed = completed.exit_code == 0 and not completed.timed_out
        if completed.timed_out:
            summary = f"tests timed out after {timeout}s"
        else:
            summary = "tests passed" if passed else f"tests failed (exit {completed.exit_code})"
        data = completed.to_dict()
        data["passed"] = passed
        return self._ok(summary, **data)
