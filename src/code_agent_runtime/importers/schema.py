"""The imported-run schema: a normalised external coding-agent run (Milestone 11).

A coding agent that is *not* this runtime — a Claude-Code-like workflow, a
manually exported transcript, a pair of before/after directories — produces a
record this runtime did not. This module defines the small, JSON-serialisable
shape every such record is normalised into before it is converted to this
runtime's own :class:`~code_agent_runtime.traces.schema.Trace` and scored with the
same scorer. It is pure data, like :mod:`code_agent_runtime.traces.schema`:
nothing here reads a directory, runs a command, or scores anything (that is
:mod:`.sources` and :mod:`.convert`).

An :class:`ImportedRun` carries three separable things, because an external run
gives us some but rarely all of them:

- **the process** — the ordered :class:`ImportedAction` stream (the external
  agent's tool calls / messages), mapped onto this runtime's tool vocabulary so
  the imported trace reads like a native one;
- **the change** — a captured ``diff`` (git-``numstat``-shaped) and, when the full
  text is available, the after-state ``files`` map (relative path → content, or
  ``None`` for a deletion). The ``files`` map is what makes *verification* possible:
  the converter can materialise the change over the task fixture and re-score it;
- **the declared outcome** — an optional ``tests`` result the source asserts (the
  external agent said its tests passed). This is *trusted* unless verification
  re-derives it.

Honesty note: an imported run is only as trustworthy as its source. A declared
``tests`` result is the source's claim, not this runtime's measurement — which is
exactly why :mod:`.convert` offers a verify mode that re-runs the task's test
command against the reconstructed workspace. The distinction is preserved
everywhere: ``source_kind`` and ``source_meta`` record where the run came from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: Imported-run schema version. Bumped only on a breaking change to the on-disk
#: shape, so a reader can refuse (or migrate) a record it does not understand.
IMPORT_SCHEMA_VERSION = 1

#: Where an imported run came from. A closed vocabulary so a typo cannot enter a
#: record silently; ``synthetic`` is a deterministic, offline Claude-Code-like run
#: this runtime generates itself (see :func:`code_agent_runtime.importers.synthesize_import`).
SOURCE_KINDS: frozenset[str] = frozenset(
    {"before_after", "diff_and_log", "transcript", "synthetic", "exported"}
)

#: Kinds of one imported action, mirroring the runtime's own step vocabulary
#: (``tool``/``finish``) plus ``message`` for a transcript turn that did no tool
#: call (preserved for the report, but not a runtime step).
ACTION_KINDS: frozenset[str] = frozenset({"tool_call", "finish", "message"})

#: Map common Claude-Code-style tool names onto this runtime's registry names, so
#: an imported ``Edit`` reads as ``apply_patch`` and an imported ``Bash`` as
#: ``run_shell``. Names already in this runtime's vocabulary map to themselves.
#: An unrecognised name is kept verbatim (and flagged by the converter) rather
#: than dropped, so nothing in the source is silently lost.
TOOL_NAME_MAP: dict[str, str] = {
    # Claude-Code-ish names.
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "apply_patch",
    "MultiEdit": "apply_patch",
    "NotebookEdit": "apply_patch",
    "Bash": "run_shell",
    "Grep": "search_repo",
    "Glob": "search_repo",
    "LS": "search_repo",
    # This runtime's own names (identity).
    "read_file": "read_file",
    "write_file": "write_file",
    "apply_patch": "apply_patch",
    "run_shell": "run_shell",
    "search_repo": "search_repo",
    "run_tests": "run_tests",
    "git_diff": "git_diff",
}

#: Effect category for each runtime tool, used to label a fabricated
#: :class:`~code_agent_runtime.tools.ToolResult` when an imported action is
#: replayed into a trace. Mirrors each tool's declared ``category``.
TOOL_CATEGORY: dict[str, str] = {
    "read_file": "read",
    "search_repo": "read",
    "git_diff": "read",
    "write_file": "write",
    "apply_patch": "write",
    "run_shell": "exec",
    "run_tests": "exec",
}


class ImportSourceError(ValueError):
    """Raised when an import source is malformed or cannot be normalised.

    Carries every problem found (not just the first) plus the source it came
    from, rendered as a readable multi-line message — matching the task loader's
    convention so import errors read the same as task-validation errors.
    """

    def __init__(self, problems: list[str], *, source: str | None = None) -> None:
        self.problems = list(problems)
        self.source = source
        header = f"invalid import source ({source})" if source else "invalid import source"
        body = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{header}:\n{body}" if body else header)


def map_tool_name(raw: str) -> str:
    """Map an external tool name onto this runtime's vocabulary (identity if unknown)."""
    return TOOL_NAME_MAP.get(raw, raw)


@dataclass(frozen=True)
class ImportedAction:
    """One action in an imported run: a tool call, a finish, or a bare message.

    ``tool`` is the runtime-mapped tool name for a ``tool_call`` (``None`` for a
    ``finish``/``message``); ``raw_tool`` preserves the external name it was mapped
    from so nothing about the source is lost. ``args`` is the call's arguments and
    ``data`` any extra observed payload (an exit code, a path), both kept compact.
    """

    seq: int
    kind: str
    tool: str | None
    raw_tool: str | None
    summary: str
    args: Mapping[str, Any] = field(default_factory=dict)
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "tool": self.tool,
            "raw_tool": self.raw_tool,
            "summary": self.summary,
            "args": dict(self.args),
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(
        cls, d: Mapping[str, Any], *, problems: list[str] | None = None
    ) -> "ImportedAction":
        kind = str(d.get("kind", "tool_call"))
        if problems is not None and kind not in ACTION_KINDS:
            problems.append(f"action {d.get('seq')!r} has unknown kind {kind!r}")
        return cls(
            seq=int(d.get("seq", 0)),
            kind=kind,
            tool=d.get("tool"),
            raw_tool=d.get("raw_tool"),
            summary=str(d.get("summary", "")),
            args=dict(d.get("args", {})),
            data=dict(d.get("data", {})),
        )


@dataclass(frozen=True)
class ImportedRun:
    """A normalised external run, ready to convert and score (Milestone 11).

    ``files`` is the *after-state* of every path the run changed — relative POSIX
    path to its final content, or ``None`` for a deletion. It is what verification
    materialises over the task fixture; an empty map means the source carried no
    file content (a diff-only or transcript-only import), so only trust-mode
    scoring is possible. ``diff`` and ``tests`` are the source's captured change
    and *declared* test outcome.
    """

    schema_version: int
    source_kind: str
    task_id: str | None
    agent_label: str
    actions: tuple[ImportedAction, ...]
    diff: Mapping[str, Any] | None = None
    tests: Mapping[str, Any] | None = None
    files: Mapping[str, str | None] = field(default_factory=dict)
    source_meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def has_after_state(self) -> bool:
        """True if the run carries file content, so verification is possible."""
        return bool(self.files)

    @property
    def unknown_tools(self) -> tuple[str, ...]:
        """External tool names that did not map onto a known runtime tool."""
        known = set(TOOL_CATEGORY)
        seen: list[str] = []
        for a in self.actions:
            if a.kind == "tool_call" and a.tool is not None and a.tool not in known:
                if a.tool not in seen:
                    seen.append(a.tool)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_kind": self.source_kind,
            "task_id": self.task_id,
            "agent_label": self.agent_label,
            "actions": [a.to_dict() for a in self.actions],
            "diff": dict(self.diff) if self.diff is not None else None,
            "tests": dict(self.tests) if self.tests is not None else None,
            "files": dict(self.files),
            "source_meta": dict(self.source_meta),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], *, source: str | None = None) -> "ImportedRun":
        """Validate a parsed import document and build an :class:`ImportedRun`.

        Collects every problem and raises a single :class:`ImportSourceError` if
        any are found, so an author sees all issues at once.
        """
        problems: list[str] = []
        if not isinstance(d, Mapping):
            raise ImportSourceError(
                [f"import document must be a mapping/object, got {type(d).__name__}"],
                source=source,
            )

        version = d.get("schema_version", IMPORT_SCHEMA_VERSION)
        if not isinstance(version, int) or isinstance(version, bool):
            problems.append("'schema_version' must be an integer")
            version = IMPORT_SCHEMA_VERSION
        elif version != IMPORT_SCHEMA_VERSION:
            problems.append(
                f"unsupported import schema version {version!r}; supported: {IMPORT_SCHEMA_VERSION}"
            )

        source_kind = d.get("source_kind")
        if source_kind not in SOURCE_KINDS:
            problems.append(
                f"'source_kind' {source_kind!r} is not recognised "
                f"(allowed: {', '.join(sorted(SOURCE_KINDS))})"
            )

        agent_label = d.get("agent_label", "claude-code-import")
        if not isinstance(agent_label, str) or not agent_label.strip():
            problems.append("'agent_label' must be a non-empty string")
            agent_label = "claude-code-import"

        raw_actions = d.get("actions", [])
        if not isinstance(raw_actions, (list, tuple)):
            problems.append(f"'actions' must be a list, got {type(raw_actions).__name__}")
            raw_actions = []
        actions = tuple(
            ImportedAction.from_dict(a, problems=problems)
            for a in raw_actions
            if isinstance(a, Mapping)
        )

        files_raw = d.get("files", {})
        if not isinstance(files_raw, Mapping):
            problems.append(f"'files' must be a mapping, got {type(files_raw).__name__}")
            files_raw = {}
        files: dict[str, str | None] = {}
        for path, content in files_raw.items():
            if not isinstance(path, str):
                problems.append(f"'files' key {path!r} must be a string path")
                continue
            if content is not None and not isinstance(content, str):
                problems.append(
                    f"'files[{path}]' must be a string or null, got {type(content).__name__}"
                )
                continue
            files[path] = content

        for key in ("diff", "tests", "source_meta"):
            val = d.get(key)
            if val is not None and not isinstance(val, Mapping):
                problems.append(f"'{key}' must be a mapping or null, got {type(val).__name__}")

        if problems:
            raise ImportSourceError(problems, source=source)

        return cls(
            schema_version=version,
            source_kind=str(source_kind),
            task_id=d.get("task_id"),
            agent_label=agent_label,
            actions=actions,
            diff=dict(d["diff"]) if d.get("diff") is not None else None,
            tests=dict(d["tests"]) if d.get("tests") is not None else None,
            files=files,
            source_meta=dict(d.get("source_meta", {})),
        )
