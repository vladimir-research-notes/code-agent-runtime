"""Fixture-path resolution for tasks (Milestone 2).

A task's ``fixture`` field names the repository snapshot a run is performed in.
This milestone does *not* build workspaces or copy fixtures (that is the
runtime's job in Milestone 4); it only resolves and validates the path so a task
that points at a non-existent fixture fails loudly at load time.

Resolution rule: a relative ``fixture`` is interpreted relative to the directory
containing the task file (``task.source_path``). This keeps tasks portable —
moving the ``tasks/`` and ``examples/`` trees together preserves the link. An
absolute ``fixture`` is used as-is. Tasks built directly from a dict (no
``source_path``) resolve relative to the current working directory.
"""

from __future__ import annotations

from pathlib import Path

from .schema import Task, TaskValidationError


def resolve_fixture(task: Task) -> Path:
    """Return the absolute filesystem path of ``task``'s fixture.

    Does not check existence; see :func:`fixture_exists` / :func:`check_fixture`.
    """
    fixture = Path(task.fixture)
    if fixture.is_absolute():
        return fixture
    base = Path(task.source_path).resolve().parent if task.source_path else Path.cwd()
    return (base / fixture).resolve()


def fixture_exists(task: Task) -> bool:
    """True if the task's fixture directory or file is present on disk."""
    return resolve_fixture(task).exists()


def check_fixture(task: Task) -> None:
    """Raise :class:`TaskValidationError` if the task's fixture is missing."""
    resolved = resolve_fixture(task)
    if not resolved.exists():
        raise TaskValidationError(
            [f"fixture path does not exist: {task.fixture!r} (resolved to {resolved})"],
            source=task.source_path,
        )
