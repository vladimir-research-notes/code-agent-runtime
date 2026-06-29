"""``search_repo`` — find text in the workspace (Milestone 3).

A dependency-free, deterministic line search: no ripgrep, no shell. It walks the
workspace, skips dotted directories and binary/oversized files, and reports
matching lines with their paths and 1-based line numbers. Substring search is the
default; pass ``regex=True`` for Python regular-expression matching.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult

#: Files larger than this are skipped (a search match in a multi-megabyte blob is
#: rarely what an agent wants and would bloat the result/trace).
_MAX_FILE_BYTES = 1_000_000

#: Per-line text is truncated to this many characters in the result.
_MAX_LINE_CHARS = 400


class SearchRepoTool(Tool):
    """Search workspace text files for a substring or regular expression."""

    name = "search_repo"
    category = "read"
    summary = "Search the workspace for a substring or regex, returning matching lines."
    params = (
        ToolParam("query", "str", required=True, description="Substring or regex to search for."),
        ToolParam(
            "regex",
            "bool",
            required=False,
            description="Treat the query as a regular expression (default: false).",
            default=False,
        ),
        ToolParam(
            "glob",
            "str",
            required=False,
            description="Only search files whose workspace-relative path matches this glob.",
        ),
        ToolParam(
            "ignore_case",
            "bool",
            required=False,
            description="Case-insensitive match (default: false).",
            default=False,
        ),
        ToolParam(
            "max_results",
            "int",
            required=False,
            description="Stop after this many matching lines (default: 200).",
            default=200,
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        query = args["query"]
        use_regex = args.get("regex", False)
        glob = args.get("glob")
        ignore_case = args.get("ignore_case", False)
        max_results = args.get("max_results", 200)
        if not query:
            raise ToolError("'query' must not be empty")
        if max_results <= 0:
            raise ToolError("'max_results' must be a positive integer")

        flags = re.IGNORECASE if ignore_case else 0
        if use_regex:
            try:
                pattern = re.compile(query, flags)
            except re.error as exc:
                raise ToolError(f"invalid regex {query!r}: {exc}") from exc
        else:
            pattern = re.compile(re.escape(query), flags)

        root = ctx.workspace.resolve()
        matches: list[dict[str, Any]] = []
        files_searched = 0
        truncated = False

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = ctx.relpath(path)
            if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
                continue  # skip dotted directories (.git, .venv, ...)
            if glob and not fnmatch.fnmatch(rel, glob):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > _MAX_FILE_BYTES or b"\x00" in raw:
                continue
            files_searched += 1
            text = raw.decode("utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(
                        {"path": rel, "line": lineno, "text": line[:_MAX_LINE_CHARS]}
                    )
                    if len(matches) >= max_results:
                        truncated = True
                        break
            if truncated:
                break

        summary = (
            f"{len(matches)} match(es) for {query!r} across {files_searched} file(s)"
            + (" [truncated]" if truncated else "")
        )
        return self._ok(
            summary,
            query=query,
            regex=use_regex,
            match_count=len(matches),
            files_searched=files_searched,
            truncated=truncated,
            matches=matches,
        )
