"""``read_file`` — read a UTF-8 text file from the workspace (Milestone 3)."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult


class ReadFileTool(Tool):
    """Read a text file under the workspace and report its contents.

    Binary files (those containing a NUL byte) are detected and reported with
    ``binary=True`` and no ``content``, rather than returning mojibake. Content
    beyond ``max_bytes`` is truncated and flagged.
    """

    name = "read_file"
    category = "read"
    summary = "Read a UTF-8 text file from the workspace."
    params = (
        ToolParam("path", "str", required=True, description="Workspace-relative file path."),
        ToolParam(
            "max_bytes",
            "int",
            required=False,
            description="Truncate content beyond this many bytes (default: context limit).",
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        path = args["path"]
        max_bytes = args.get("max_bytes", ctx.max_output_bytes)
        if max_bytes <= 0:
            raise ToolError("'max_bytes' must be a positive integer")

        resolved = ctx.resolve(path)
        if not resolved.exists():
            raise ToolError(f"file does not exist: {path!r}")
        if not resolved.is_file():
            raise ToolError(f"not a regular file: {path!r}")

        raw = resolved.read_bytes()
        total_bytes = len(raw)
        rel = ctx.relpath(resolved)

        if b"\x00" in raw:
            return self._ok(
                f"read {rel} (binary, {total_bytes} bytes)",
                path=rel,
                bytes=total_bytes,
                binary=True,
                truncated=False,
                lines=0,
                content=None,
            )

        truncated = total_bytes > max_bytes
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        return self._ok(
            f"read {rel} ({total_bytes} bytes, {lines} lines)"
            + (" [truncated]" if truncated else ""),
            path=rel,
            bytes=total_bytes,
            binary=False,
            truncated=truncated,
            lines=lines,
            content=text,
        )
