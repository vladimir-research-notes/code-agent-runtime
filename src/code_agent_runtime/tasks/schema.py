"""Versioned coding-agent task schema (Milestone 2).

A *task* is a small, version-controlled description of one unit of work for a
coding agent: what to do (``prompt``), where to do it (``fixture``), what the
agent is allowed to do (``allowed_tools``, ``timeout_seconds``,
``resource_limits``), and how success is judged (``scoring_method``,
``test_command``). Tasks are declarative data; nothing here executes an agent,
runs a command, or builds a workspace. Those subsystems arrive in later
milestones (see ``docs/PLAN.md``); this module only defines and validates the
on-disk contract they will consume.

Design goals for this milestone:

- **Strict, readable validation.** A malformed task should fail with a list of
  human-readable problems naming the offending field, not a stack trace. All
  problems are collected and reported together (see :class:`TaskValidationError`).
- **Closed vocabularies.** ``allowed_tools`` and ``scoring_method`` are checked
  against the names the planned runtime will recognise, so typos are caught at
  authoring time rather than at run time.
- **Format-agnostic core.** Validation operates on a plain ``dict`` (already
  parsed from JSON or YAML by :mod:`code_agent_runtime.tasks.loader`), so the
  schema has no parsing or filesystem concerns of its own.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

#: Current task-schema version. Tasks must declare a ``version`` in
#: :data:`SUPPORTED_VERSIONS`; bumping this is how breaking schema changes are
#: introduced without silently misreading older files.
SCHEMA_VERSION = 1
SUPPORTED_VERSIONS: frozenset[int] = frozenset({1})

#: Tool names the runtime's tool registry will expose (Milestone 3). Validating
#: ``allowed_tools`` against this closed set turns a typo (``read-file``) into an
#: authoring-time error instead of a silent no-op at run time.
KNOWN_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "write_file",
        "apply_patch",
        "run_shell",
        "git_diff",
        "run_tests",
        "search_repo",
    }
)

#: Recognised scoring methods (implemented in Milestone 8). ``none`` marks a task
#: that is not automatically scored (e.g. a sandbox-policy demonstration judged
#: by inspection).
SCORING_METHODS: frozenset[str] = frozenset(
    {
        "test_command",  # pass iff the test command exits 0
        "expected_files",  # pass iff named files exist / match
        "diff_constraint",  # pass iff the change stays within a file scope
        "custom",  # pass per a custom scorer hook
        "none",  # not automatically scored
    }
)

#: Default agent wall-clock budget when a task omits ``timeout_seconds``.
DEFAULT_TIMEOUT_SECONDS = 300

#: Valid task id shape: lowercase alphanumerics with ``-``/``_``/``.``/``/``
#: separators (``/`` allows namespacing like ``bugfix/sum-range``).
_ID_RE = re.compile(r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$")

#: Keys recognised at the top level of a task document. Anything else is a
#: validation error so typos surface immediately.
_KNOWN_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "id",
        "title",
        "prompt",
        "fixture",
        "allowed_tools",
        "timeout_seconds",
        "scoring_method",
        "test_command",
        "resource_limits",
        "metadata",
    }
)

_KNOWN_LIMIT_KEYS: frozenset[str] = frozenset(
    {"cpu_seconds", "memory_mb", "max_output_bytes", "network"}
)


class TaskValidationError(ValueError):
    """Raised when a task document fails validation.

    Carries *all* discovered problems (not just the first) plus the source the
    task came from, and renders them as a readable, multi-line message.
    """

    def __init__(self, problems: list[str], *, source: str | None = None) -> None:
        self.problems = list(problems)
        self.source = source
        header = f"invalid task ({source})" if source else "invalid task"
        body = "\n".join(f"  - {p}" for p in self.problems)
        super().__init__(f"{header}:\n{body}" if body else header)


@dataclass(frozen=True)
class ResourceLimits:
    """Declarative resource bounds for a run.

    These are *intent* expressed by the task author. Enforcement (process limits,
    network isolation) is the sandbox's job in Milestone 7; this milestone only
    parses and validates the declaration. ``None`` means "unspecified / use the
    runtime default"; ``network`` defaults to ``False`` (deny).
    """

    cpu_seconds: int | None = None
    memory_mb: int | None = None
    max_output_bytes: int | None = None
    network: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Task:
    """A validated, versioned coding-agent task.

    Construct via :func:`validate_task_dict` (or the loader), never by hand from
    untrusted data — the dataclass itself performs no validation.
    """

    id: str
    title: str
    prompt: str
    fixture: str
    scoring_method: str
    version: int
    allowed_tools: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    #: Normalised argv for the scoring/test command, or ``None`` when the task is
    #: not scored by a command. A string in the source is shell-split into argv.
    test_command: tuple[str, ...] | None = None
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    #: Absolute path of the file this task was loaded from, set by the loader.
    #: ``None`` for tasks built directly from a dict.
    source_path: str | None = None

    @property
    def test_command_str(self) -> str | None:
        """The test command rendered back to a copy-pasteable shell string."""
        if self.test_command is None:
            return None
        return shlex.join(self.test_command)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict (round-trips through the loader)."""
        return {
            "version": self.version,
            "id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "fixture": self.fixture,
            "allowed_tools": list(self.allowed_tools),
            "timeout_seconds": self.timeout_seconds,
            "scoring_method": self.scoring_method,
            "test_command": list(self.test_command) if self.test_command is not None else None,
            "resource_limits": self.resource_limits.to_dict(),
            "metadata": dict(self.metadata),
            "source_path": self.source_path,
        }


def _require(problems: list[str], data: Mapping[str, Any], key: str) -> bool:
    if key not in data:
        problems.append(f"missing required field '{key}'")
        return False
    return True


def _check_str(problems: list[str], data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if not isinstance(value, str):
        problems.append(f"'{key}' must be a string, got {type(value).__name__}")
        return None
    if not value.strip():
        problems.append(f"'{key}' must not be empty")
        return None
    return value


def _validate_resource_limits(problems: list[str], raw: Any) -> ResourceLimits:
    if not isinstance(raw, Mapping):
        problems.append(f"'resource_limits' must be a mapping, got {type(raw).__name__}")
        return ResourceLimits()
    unknown = set(raw) - _KNOWN_LIMIT_KEYS
    if unknown:
        problems.append(
            f"'resource_limits' has unknown key(s): {', '.join(sorted(unknown))} "
            f"(allowed: {', '.join(sorted(_KNOWN_LIMIT_KEYS))})"
        )
    fields: dict[str, Any] = {}
    for key in ("cpu_seconds", "memory_mb", "max_output_bytes"):
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        # bool is an int subclass; reject it explicitly so True/False aren't sizes.
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            problems.append(f"'resource_limits.{key}' must be a positive integer")
        else:
            fields[key] = value
    if "network" in raw:
        if not isinstance(raw["network"], bool):
            problems.append("'resource_limits.network' must be a boolean")
        else:
            fields["network"] = raw["network"]
    return ResourceLimits(**fields)


def _normalise_test_command(problems: list[str], raw: Any) -> tuple[str, ...] | None:
    """Accept a shell string or an argv list; return normalised argv."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if not raw.strip():
            problems.append("'test_command' string must not be empty")
            return None
        try:
            argv = shlex.split(raw)
        except ValueError as exc:
            problems.append(f"'test_command' is not a valid shell string: {exc}")
            return None
        if not argv:
            problems.append("'test_command' string must not be empty")
            return None
        return tuple(argv)
    if isinstance(raw, (list, tuple)):
        if not raw:
            problems.append("'test_command' list must not be empty")
            return None
        if not all(isinstance(part, str) for part in raw):
            problems.append("'test_command' list must contain only strings")
            return None
        return tuple(raw)
    problems.append(f"'test_command' must be a string or list of strings, got {type(raw).__name__}")
    return None


def validate_task_dict(data: Any, *, source: str | None = None) -> Task:
    """Validate a parsed task document and return a :class:`Task`.

    Collects every problem it can find and raises a single
    :class:`TaskValidationError` if there are any, so an author sees all issues
    at once rather than fixing them one error per run.
    """
    problems: list[str] = []

    if not isinstance(data, Mapping):
        raise TaskValidationError(
            [f"task document must be a mapping/object, got {type(data).__name__}"],
            source=source,
        )

    unknown = set(data) - _KNOWN_KEYS
    if unknown:
        problems.append(
            f"unknown field(s): {', '.join(sorted(unknown))} "
            f"(allowed: {', '.join(sorted(_KNOWN_KEYS))})"
        )

    # version ---------------------------------------------------------------
    if _require(problems, data, "version"):
        version = data["version"]
        if not isinstance(version, int) or isinstance(version, bool):
            problems.append("'version' must be an integer")
        elif version not in SUPPORTED_VERSIONS:
            problems.append(
                f"unsupported task version {version!r}; "
                f"supported: {sorted(SUPPORTED_VERSIONS)}"
            )

    # id --------------------------------------------------------------------
    task_id = _check_str(problems, data, "id") if _require(problems, data, "id") else None
    if task_id is not None and not _ID_RE.match(task_id):
        problems.append(
            f"'id' {task_id!r} must be lowercase alphanumerics separated by - _ . / "
        )

    # plain required strings ------------------------------------------------
    for key in ("title", "prompt", "fixture"):
        if _require(problems, data, key):
            _check_str(problems, data, key)

    # scoring_method --------------------------------------------------------
    scoring_method = None
    if _require(problems, data, "scoring_method"):
        scoring_method = data["scoring_method"]
        if scoring_method not in SCORING_METHODS:
            problems.append(
                f"'scoring_method' {scoring_method!r} is not recognised "
                f"(allowed: {', '.join(sorted(SCORING_METHODS))})"
            )

    # allowed_tools ---------------------------------------------------------
    allowed_tools: tuple[str, ...] = ()
    raw_tools = data.get("allowed_tools", [])
    if not isinstance(raw_tools, (list, tuple)):
        problems.append(f"'allowed_tools' must be a list, got {type(raw_tools).__name__}")
    else:
        unknown_tools = [t for t in raw_tools if t not in KNOWN_TOOLS]
        if unknown_tools:
            problems.append(
                f"'allowed_tools' has unknown tool(s): {', '.join(map(str, unknown_tools))} "
                f"(known: {', '.join(sorted(KNOWN_TOOLS))})"
            )
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        allowed_tools = tuple(
            t for t in raw_tools if isinstance(t, str) and not (t in seen or seen.add(t))
        )

    # timeout_seconds -------------------------------------------------------
    timeout_seconds = DEFAULT_TIMEOUT_SECONDS
    if "timeout_seconds" in data:
        value = data["timeout_seconds"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            problems.append("'timeout_seconds' must be a positive integer")
        else:
            timeout_seconds = value

    # test_command (required when scoring by a command) ---------------------
    test_command = _normalise_test_command(problems, data.get("test_command"))
    if scoring_method == "test_command" and test_command is None:
        problems.append("scoring_method 'test_command' requires a non-empty 'test_command'")

    # resource_limits -------------------------------------------------------
    resource_limits = _validate_resource_limits(problems, data.get("resource_limits", {}))

    # metadata --------------------------------------------------------------
    metadata = data.get("metadata", {})
    if not isinstance(metadata, Mapping):
        problems.append(f"'metadata' must be a mapping, got {type(metadata).__name__}")
        metadata = {}

    if problems:
        raise TaskValidationError(problems, source=source)

    return Task(
        id=task_id,  # type: ignore[arg-type]  (validated above)
        title=data["title"],
        prompt=data["prompt"],
        fixture=data["fixture"],
        scoring_method=scoring_method,  # type: ignore[arg-type]
        version=data["version"],
        allowed_tools=allowed_tools,
        timeout_seconds=timeout_seconds,
        test_command=test_command,
        resource_limits=resource_limits,
        metadata=dict(metadata),
        source_path=source,
    )
