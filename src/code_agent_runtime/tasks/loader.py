"""Loading and discovery of task files (Milestone 2).

The canonical on-disk format is **JSON** (``*.task.json``), which keeps the core
package dependency-free and the default test suite free and offline. **YAML**
(``*.task.yaml`` / ``*.task.yml``) is supported *optionally*: it is only parsed
when PyYAML is importable, and a missing PyYAML produces a clear, actionable
error rather than an obscure import failure.

Two layers:

- :func:`parse_task_text` / :func:`load_task` — parse one document and validate
  it into a :class:`~code_agent_runtime.tasks.schema.Task`;
- :func:`discover_task_files` / :func:`discover_tasks` / :func:`find_task` —
  locate task files under a directory and load them.

Parsing and validation errors are surfaced as
:class:`~code_agent_runtime.tasks.schema.TaskValidationError` with the offending
file named, so callers (the CLI, tests) can present readable diagnostics.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .fixtures import check_fixture
from .schema import Task, TaskValidationError, validate_task_dict

#: Filename suffixes that mark a task document, mapped to a parser format key.
TASK_SUFFIXES: dict[str, str] = {
    ".task.json": "json",
    ".task.yaml": "yaml",
    ".task.yml": "yaml",
}


def _format_for(path: Path) -> str | None:
    """Return the parser format for a task file, or ``None`` if not a task file."""
    name = path.name.lower()
    for suffix, fmt in TASK_SUFFIXES.items():
        if name.endswith(suffix):
            return fmt
    return None


def parse_task_text(text: str, *, fmt: str, source: str | None = None) -> object:
    """Parse raw task text into a Python object (typically a ``dict``).

    ``fmt`` is ``"json"`` or ``"yaml"``. Raises :class:`TaskValidationError` on a
    syntax error or, for YAML, when PyYAML is not installed.
    """
    if fmt == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise TaskValidationError([f"invalid JSON: {exc}"], source=source) from exc
    if fmt == "yaml":
        try:
            import yaml  # optional dependency; only needed for YAML tasks
        except ModuleNotFoundError as exc:
            raise TaskValidationError(
                [
                    "YAML task files require PyYAML, which is not installed. "
                    "Install it (`pip install pyyaml`) or use the canonical "
                    "JSON format (*.task.json)."
                ],
                source=source,
            ) from exc
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise TaskValidationError([f"invalid YAML: {exc}"], source=source) from exc
    raise ValueError(f"unknown task format {fmt!r}")


def load_task(path: str | Path, *, resolve_fixture: bool = True) -> Task:
    """Load and validate a single task file.

    With ``resolve_fixture=True`` (the default) the task's ``fixture`` path is
    additionally checked to exist on disk relative to the task file; a missing
    fixture is a :class:`TaskValidationError`. Pass ``resolve_fixture=False`` to
    validate the schema only (useful when authoring a task before its fixture
    exists, or when listing tasks without touching the filesystem).
    """
    path = Path(path)
    source = str(path)
    fmt = _format_for(path)
    if fmt is None:
        raise TaskValidationError(
            [
                f"unrecognised task filename {path.name!r}; expected one of: "
                + ", ".join(sorted(TASK_SUFFIXES))
            ],
            source=source,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TaskValidationError([f"cannot read task file: {exc}"], source=source) from exc

    data = parse_task_text(text, fmt=fmt, source=source)
    task = validate_task_dict(data, source=source)
    if resolve_fixture:
        check_fixture(task)
    return task


def discover_task_files(root: str | Path) -> list[Path]:
    """Return task files under ``root`` (recursively), sorted by path.

    A path that is itself a task file is returned as-is. Hidden directories
    (``.git``, ``.venv``, ...) are skipped.
    """
    root = Path(root)
    if root.is_file():
        return [root] if _format_for(root) else []
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue  # skip dotted directories
        if _format_for(path):
            found.append(path)
    return sorted(found)


def discover_tasks(root: str | Path, *, resolve_fixture: bool = True) -> list[Task]:
    """Load every task under ``root``. Raises on the first invalid task.

    Use this for trusted task trees (e.g. the repository's ``tasks/``) where any
    invalid task should be a hard error. For robust, best-effort listing that
    keeps going past bad files, iterate :func:`discover_task_files` and call
    :func:`load_task` in a ``try``/``except`` (this is what the CLI does).
    """
    return [load_task(p, resolve_fixture=resolve_fixture) for p in discover_task_files(root)]


def find_task(root: str | Path, ident: str, *, resolve_fixture: bool = True) -> Task:
    """Resolve ``ident`` to a single task, by file path or by task ``id``.

    ``ident`` may be a path to a task file or a task id discovered under
    ``root``. Raises :class:`TaskValidationError` if nothing matches or if an id
    is ambiguous across multiple files.
    """
    as_path = Path(ident)
    if as_path.is_file() and _format_for(as_path):
        return load_task(as_path, resolve_fixture=resolve_fixture)

    matches: list[Task] = []
    for path in discover_task_files(root):
        try:
            task = load_task(path, resolve_fixture=False)
        except TaskValidationError:
            continue  # ignore unrelated invalid files while searching by id
        if task.id == ident:
            matches.append(load_task(path, resolve_fixture=resolve_fixture))
    if not matches:
        raise TaskValidationError(
            [f"no task found with id or path {ident!r} under {Path(root)}"]
        )
    if len(matches) > 1:
        where = ", ".join(sorted(t.source_path or "?" for t in matches))
        raise TaskValidationError([f"task id {ident!r} is ambiguous; found in: {where}"])
    return matches[0]


def load_many(paths: Iterable[str | Path], *, resolve_fixture: bool = True) -> list[Task]:
    """Convenience: load a fixed list of task files."""
    return [load_task(p, resolve_fixture=resolve_fixture) for p in paths]
