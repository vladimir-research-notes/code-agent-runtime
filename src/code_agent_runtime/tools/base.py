"""Core tool abstractions (Milestone 3).

A *tool* is the only way an agent acts on a workspace. Every tool in this
runtime shares one shape so the runtime can dispatch them uniformly and the
tracer can record them faithfully:

- a static :class:`ToolSpec` (name, category, parameter list) that describes the
  tool without running it — used by the registry, the CLI, and tracing;
- a :meth:`Tool.run` entry point that validates arguments against the spec and
  returns a structured :class:`ToolResult` (never a bare string, never an
  uncaught operational exception);
- a :class:`ToolContext` that pins the *workspace* the tool may touch and the
  output/time budgets it must respect.

Two design rules motivate the shapes here:

- **Structured results for tracing.** A run is only as replayable as its trace.
  Each tool returns a JSON-serialisable :class:`ToolResult` whose ``data`` holds
  the tool-specific payload and whose ``ok``/``error`` fields make failures
  first-class records rather than exceptions that vanish from the trace.
- **Workspace confinement by default.** Path-taking tools resolve every path
  through :meth:`ToolContext.resolve`, which refuses to escape the workspace
  root. This is a *baseline* containment guard, not the full permission policy
  (allow/deny lists, secret scanning, network isolation) — that is Milestone 7.
  It is implemented here because letting a tool read or clobber arbitrary host
  files by default would be indefensible even in a scaffold.

Results deliberately carry **no wall-clock timing**: timestamps and durations
belong to the trace recorder (Milestone 5), and keeping them out of the result
keeps tool outputs deterministic and unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar

#: Default ceiling on captured subprocess output, in bytes. Output beyond this is
#: truncated and flagged so a runaway command cannot blow up a trace.
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024

#: Default per-tool wall-clock budget for subprocess-running tools, in seconds.
DEFAULT_TOOL_TIMEOUT_SECONDS = 120

#: Closed vocabulary of tool effect categories. ``read`` observes the workspace,
#: ``write`` mutates files in it, ``exec`` runs a subprocess. The category drives
#: how aggressively the sandbox (Milestone 7) will gate a tool.
TOOL_CATEGORIES: frozenset[str] = frozenset({"read", "write", "exec"})

#: Parameter type tokens understood by the light argument validator below.
_PARAM_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "bool": (bool,),
    "str|list": (str, list, tuple),
    "mapping": (Mapping,),
}


class ToolError(Exception):
    """Raised inside a tool to signal an *anticipated* operational failure.

    The base :meth:`Tool.run` catches this and converts it into a failed
    :class:`ToolResult` (``ok=False``), so expected failures — a missing file, a
    path that escapes the workspace, a malformed patch, a non-git workspace —
    become structured, traceable records rather than stack traces. Programmer
    errors (a bug in a tool) are *not* wrapped: they propagate so tests catch
    them.
    """


@dataclass(frozen=True)
class ToolParam:
    """One declared parameter of a tool, for validation and introspection."""

    name: str
    type: str
    required: bool
    description: str
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolSpec:
    """Static description of a tool: enough to list, document, and trace it."""

    name: str
    category: str
    summary: str
    params: tuple[ToolParam, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "params": [p.to_dict() for p in self.params],
        }


@dataclass(frozen=True)
class ToolContext:
    """Execution context shared by every tool call.

    ``workspace`` is the only directory tools may read or write by default; it is
    resolved (symlinks included) so confinement checks compare real paths.
    ``max_output_bytes`` and ``timeout_seconds`` bound subprocess-running tools.
    """

    workspace: Path
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS

    @classmethod
    def for_dir(
        cls,
        path: str | Path,
        *,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS,
    ) -> ToolContext:
        """Build a context rooted at ``path`` (resolved to an absolute path)."""
        return cls(
            workspace=Path(path).resolve(),
            max_output_bytes=max_output_bytes,
            timeout_seconds=timeout_seconds,
        )

    def resolve(self, rel: str | Path) -> Path:
        """Resolve ``rel`` inside the workspace, refusing to escape it.

        Relative paths are taken from the workspace root; an absolute path is
        accepted only if it lands inside the workspace. Symlinks are resolved
        before the containment check, so a link pointing outside is rejected.
        Raises :class:`ToolError` on any escape — including ``..`` traversal.
        """
        root = self.workspace.resolve()
        candidate = Path(rel)
        combined = candidate if candidate.is_absolute() else root / candidate
        resolved = combined.resolve()
        if resolved != root and not resolved.is_relative_to(root):
            raise ToolError(
                f"path {str(rel)!r} escapes the workspace ({resolved} is outside {root})"
            )
        return resolved

    def relpath(self, resolved: str | Path) -> str:
        """Render an absolute, workspace-confined path back as a relative string.

        Used so results report portable, workspace-relative paths rather than
        absolute host paths. Falls back to the absolute path if (defensively) the
        path is not under the workspace.
        """
        root = self.workspace.resolve()
        path = Path(resolved).resolve()
        try:
            rel = path.relative_to(root)
        except ValueError:  # pragma: no cover - callers pass confined paths
            return str(path)
        return str(rel) if str(rel) != "." else ""


@dataclass(frozen=True)
class ToolResult:
    """Structured, JSON-serialisable result of a single tool call.

    ``data`` holds the tool-specific payload (file contents, a diff, a match
    list, a subprocess's exit code and output). ``summary`` is a one-line human
    description for logs and reports. ``ok``/``error`` make success and failure
    explicit and recordable.
    """

    tool: str
    category: str
    ok: bool
    summary: str
    data: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "category": self.category,
            "ok": self.ok,
            "summary": self.summary,
            "data": dict(self.data),
            "error": self.error,
        }


class Tool:
    """Base class for a structured, traceable tool.

    Subclasses set the class attributes :attr:`name`, :attr:`category`,
    :attr:`summary`, and :attr:`params`, and implement :meth:`_run`. They never
    override :meth:`run`: the base implementation validates arguments against the
    spec and turns an anticipated :class:`ToolError` into a failed result, so
    every subclass body can assume valid arguments and may simply ``raise
    ToolError`` on operational problems.
    """

    #: Unique tool name (must be a member of the registry's vocabulary).
    name: ClassVar[str] = ""
    #: One of :data:`TOOL_CATEGORIES`.
    category: ClassVar[str] = "read"
    #: One-line description used by ``tools list`` and tracing.
    summary: ClassVar[str] = ""
    #: Declared parameters, used for validation and introspection.
    params: ClassVar[tuple[ToolParam, ...]] = ()

    def __init__(self) -> None:
        if self.category not in TOOL_CATEGORIES:
            raise ValueError(
                f"tool {self.name!r} has unknown category {self.category!r} "
                f"(allowed: {', '.join(sorted(TOOL_CATEGORIES))})"
            )

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            category=self.category,
            summary=self.summary,
            params=tuple(self.params),
        )

    # -- public entry point -------------------------------------------------

    def run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        """Validate ``args`` against the spec and dispatch to :meth:`_run`."""
        try:
            self._validate_args(args)
            result = self._run(ctx, **args)
        except ToolError as exc:
            return self._fail(str(exc))
        if not isinstance(result, ToolResult):  # pragma: no cover - defensive
            raise TypeError(f"tool {self.name!r} returned {type(result).__name__}, not ToolResult")
        return result

    # -- helpers for subclasses --------------------------------------------

    def _ok(self, summary: str, **data: Any) -> ToolResult:
        return ToolResult(
            tool=self.name, category=self.category, ok=True, summary=summary, data=data
        )

    def _fail(self, error: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            category=self.category,
            ok=False,
            summary=error,
            data={},
            error=error,
        )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:  # pragma: no cover
        raise NotImplementedError

    # -- argument validation ------------------------------------------------

    def _validate_args(self, args: Mapping[str, Any]) -> None:
        declared = {p.name: p for p in self.params}
        unknown = set(args) - set(declared)
        if unknown:
            raise ToolError(
                f"unknown argument(s) for {self.name!r}: {', '.join(sorted(unknown))} "
                f"(accepted: {', '.join(sorted(declared)) or 'none'})"
            )
        for param in self.params:
            if param.name not in args:
                if param.required:
                    raise ToolError(f"missing required argument {param.name!r} for {self.name!r}")
                continue
            value = args[param.name]
            allowed = _PARAM_TYPES.get(param.type)
            if allowed is None:  # pragma: no cover - guards a typo in a tool def
                raise ValueError(f"tool {self.name!r} declares unknown param type {param.type!r}")
            # bool is an int subclass; only the 'bool' token may accept a bool.
            if param.type != "bool" and isinstance(value, bool):
                raise ToolError(f"argument {param.name!r} must be {param.type}, got bool")
            if not isinstance(value, allowed):
                raise ToolError(
                    f"argument {param.name!r} must be {param.type}, got {type(value).__name__}"
                )
