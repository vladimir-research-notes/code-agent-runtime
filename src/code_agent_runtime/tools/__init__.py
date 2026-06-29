"""Structured tools and the tool registry (Milestone 3).

Tools are the only way an agent acts on a workspace. Every tool shares one shape
— a static :class:`ToolSpec`, a validated :meth:`Tool.run` entry point, and a
JSON-serialisable :class:`ToolResult` — so the runtime can dispatch them
uniformly and the tracer can record them faithfully. All path-taking tools are
confined to the :class:`ToolContext`'s workspace.

Public API:

- core types from :mod:`.base`: :class:`Tool`, :class:`ToolContext`,
  :class:`ToolResult`, :class:`ToolSpec`, :class:`ToolParam`, :class:`ToolError`,
  and :data:`TOOL_CATEGORIES`;
- the registry from :mod:`.registry`: :class:`ToolRegistry`, :class:`ToolCall`,
  :func:`build_registry`, and :data:`REGISTERED_TOOL_NAMES`;
- the seven tool classes.

Full containment (allow/deny paths, secret scanning, network policy) is the
sandbox's job in Milestone 7; this milestone provides workspace confinement and
bounded subprocess output/time only.
"""

from __future__ import annotations

from .apply_patch import ApplyPatchTool
from .base import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    TOOL_CATEGORIES,
    Tool,
    ToolContext,
    ToolError,
    ToolParam,
    ToolResult,
    ToolSpec,
)
from .git_diff import GitDiffTool
from .read_file import ReadFileTool
from .registry import (
    REGISTERED_TOOL_NAMES,
    ToolCall,
    ToolRegistry,
    build_registry,
)
from .run_shell import RunShellTool
from .run_tests import DEFAULT_TEST_COMMAND, RunTestsTool
from .search_repo import SearchRepoTool
from .write_file import WriteFileTool

__all__ = [
    # base
    "Tool",
    "ToolContext",
    "ToolResult",
    "ToolSpec",
    "ToolParam",
    "ToolError",
    "TOOL_CATEGORIES",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    # registry
    "ToolRegistry",
    "ToolCall",
    "build_registry",
    "REGISTERED_TOOL_NAMES",
    # tools
    "ReadFileTool",
    "WriteFileTool",
    "ApplyPatchTool",
    "RunShellTool",
    "GitDiffTool",
    "RunTestsTool",
    "SearchRepoTool",
    "DEFAULT_TEST_COMMAND",
]
