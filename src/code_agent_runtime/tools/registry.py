"""Tool registry (Milestone 3).

The registry is the single place that knows which tools exist. It maps names to
:class:`~code_agent_runtime.tools.base.Tool` instances, exposes their specs for
listing/tracing, and dispatches a :class:`ToolCall` to the right tool — always
returning a structured :class:`~code_agent_runtime.tools.base.ToolResult`, even
for an unknown tool name, so nothing an agent does escapes the trace.

:data:`REGISTERED_TOOL_NAMES` is the authoritative set of tool names. The task
schema's ``KNOWN_TOOLS`` vocabulary must equal it; a test asserts they match, so
adding a tool here without updating the schema (or vice versa) fails CI rather
than silently letting a task reference a tool that cannot run.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .apply_patch import ApplyPatchTool
from .base import Tool, ToolContext, ToolResult, ToolSpec
from .git_diff import GitDiffTool
from .read_file import ReadFileTool
from .run_shell import RunShellTool
from .run_tests import RunTestsTool
from .search_repo import SearchRepoTool
from .write_file import WriteFileTool

#: All tool classes the registry exposes. Order is the natural read→write→exec
#: grouping used by ``tools list``.
_TOOL_CLASSES: tuple[type[Tool], ...] = (
    ReadFileTool,
    SearchRepoTool,
    GitDiffTool,
    WriteFileTool,
    ApplyPatchTool,
    RunShellTool,
    RunTestsTool,
)

#: Authoritative tool-name vocabulary (kept in sync with ``tasks.KNOWN_TOOLS``).
REGISTERED_TOOL_NAMES: frozenset[str] = frozenset(cls.name for cls in _TOOL_CLASSES)


@dataclass(frozen=True)
class ToolCall:
    """A request to run a tool: its name and keyword arguments."""

    tool: str
    args: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "args": dict(self.args)}


class ToolRegistry:
    """An ordered, name-indexed collection of tools."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        mapping: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in mapping:
                raise ValueError(f"duplicate tool name in registry: {tool.name!r}")
            mapping[tool.name] = tool
        self._tools = mapping

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def tools(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def get(self, name: str) -> Tool:
        """Return the tool named ``name`` or raise :class:`KeyError`."""
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(
                f"unknown tool {name!r} (known: {', '.join(sorted(self._tools))})"
            ) from None

    def subset(self, names: Iterable[str]) -> ToolRegistry:
        """Return a new registry containing only the named tools (order kept).

        Raises :class:`KeyError` if any name is not registered, so a task that
        allows an unknown tool fails loudly rather than silently dropping it.
        """
        wanted = list(dict.fromkeys(names))  # de-dupe, preserve order
        unknown = [n for n in wanted if n not in self._tools]
        if unknown:
            raise KeyError(f"unknown tool(s): {', '.join(unknown)}")
        return ToolRegistry(self._tools[n] for n in wanted)

    def dispatch(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Run ``call`` against this registry, returning a structured result.

        An unknown tool name yields a failed result (rather than an exception) so
        the runtime can record the attempt in the trace.
        """
        tool = self._tools.get(call.tool)
        if tool is None:
            return ToolResult(
                tool=call.tool,
                category="unknown",
                ok=False,
                summary=f"unknown tool {call.tool!r}",
                error=f"unknown tool {call.tool!r} (known: {', '.join(sorted(self._tools))})",
            )
        return tool.run(ctx, **dict(call.args))


def build_registry() -> ToolRegistry:
    """Construct the default registry with one instance of every core tool."""
    return ToolRegistry(cls() for cls in _TOOL_CLASSES)
