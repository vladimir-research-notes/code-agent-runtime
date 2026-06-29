"""``write_file`` — create or overwrite a text file in the workspace (Milestone 3)."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult


class WriteFileTool(Tool):
    """Write UTF-8 text to a workspace-relative path.

    Parent directories are created when ``create_parents`` is true (the default).
    Writing over an existing file requires ``overwrite`` (also the default true);
    set it false to make the call fail rather than clobber an existing file. The
    result reports whether the file existed before and how its size changed, so a
    trace can show the effect of the write.
    """

    name = "write_file"
    category = "write"
    summary = "Create or overwrite a UTF-8 text file in the workspace."
    params = (
        ToolParam("path", "str", required=True, description="Workspace-relative file path."),
        ToolParam("content", "str", required=True, description="Full file contents to write."),
        ToolParam(
            "create_parents",
            "bool",
            required=False,
            description="Create missing parent directories (default: true).",
            default=True,
        ),
        ToolParam(
            "overwrite",
            "bool",
            required=False,
            description="Allow overwriting an existing file (default: true).",
            default=True,
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        path = args["path"]
        content = args["content"]
        create_parents = args.get("create_parents", True)
        overwrite = args.get("overwrite", True)

        resolved = ctx.resolve(path)
        if resolved.is_dir():
            raise ToolError(f"refusing to write over a directory: {path!r}")
        existed_before = resolved.exists()
        if existed_before and not overwrite:
            raise ToolError(f"file exists and overwrite is disabled: {path!r}")

        bytes_before = resolved.stat().st_size if existed_before else 0
        if not resolved.parent.exists():
            if not create_parents:
                raise ToolError(f"parent directory does not exist: {path!r}")
            resolved.parent.mkdir(parents=True, exist_ok=True)

        payload = content.encode("utf-8")
        resolved.write_bytes(payload)
        rel = ctx.relpath(resolved)
        verb = "overwrote" if existed_before else "created"
        return self._ok(
            f"{verb} {rel} ({len(payload)} bytes)",
            path=rel,
            bytes_written=len(payload),
            created=not existed_before,
            existed_before=existed_before,
            bytes_before=bytes_before,
        )
