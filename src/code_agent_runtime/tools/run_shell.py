"""``run_shell`` — run a single command in the workspace (Milestone 3).

The command runs with no shell (see :mod:`._exec`): a string is split with shell
quoting rules but pipes, redirects, and variable expansion are not interpreted.
This is exec-category and intentionally unsandboxed beyond output/time bounds;
real containment is Milestone 7.
"""

from __future__ import annotations

from typing import Any

from ._exec import normalize_argv, run_command
from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult


class RunShellTool(Tool):
    """Run a command (argv list or quoted string) and capture its result."""

    name = "run_shell"
    category = "exec"
    summary = "Run a single command in the workspace (no shell; output/time bounded)."
    params = (
        ToolParam(
            "command",
            "str|list",
            required=True,
            description="Command as a quoted string or an argv list (run without a shell).",
        ),
        ToolParam(
            "timeout_seconds",
            "int",
            required=False,
            description="Override the context's wall-clock budget for this command.",
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        argv = normalize_argv(args["command"])
        timeout = args.get("timeout_seconds", ctx.timeout_seconds)
        if timeout <= 0:
            raise ToolError("'timeout_seconds' must be a positive integer")

        completed = run_command(
            argv,
            cwd=ctx.workspace,
            timeout_seconds=timeout,
            max_output_bytes=ctx.max_output_bytes,
        )
        if completed.timed_out:
            summary = f"command timed out after {timeout}s: {argv[0]}"
        else:
            summary = f"{argv[0]} exited {completed.exit_code}"
        # A non-zero exit is a real outcome to record, not a tool failure:
        # the call succeeded in running the command. ok reflects "ran", and the
        # exit code lives in data for scorers and traces to interpret.
        return self._ok(summary, **completed.to_dict())
