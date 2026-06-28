"""Versioned coding-agent task definitions (Milestone 2).

Public API:

- :class:`Task`, :class:`ResourceLimits`, :class:`TaskValidationError` and the
  vocabularies (:data:`KNOWN_TOOLS`, :data:`SCORING_METHODS`,
  :data:`SCHEMA_VERSION`) from :mod:`.schema`;
- :func:`validate_task_dict` to validate an already-parsed document;
- :func:`load_task`, :func:`discover_tasks`, :func:`discover_task_files`,
  :func:`find_task` from :mod:`.loader`;
- :func:`resolve_fixture`, :func:`fixture_exists`, :func:`check_fixture` from
  :mod:`.fixtures`.

Tasks are declarative data only — nothing here runs an agent or a command.
"""

from __future__ import annotations

from .fixtures import check_fixture, fixture_exists, resolve_fixture
from .loader import (
    discover_task_files,
    discover_tasks,
    find_task,
    load_task,
    parse_task_text,
)
from .schema import (
    DEFAULT_TIMEOUT_SECONDS,
    KNOWN_TOOLS,
    SCHEMA_VERSION,
    SCORING_METHODS,
    SUPPORTED_VERSIONS,
    ResourceLimits,
    Task,
    TaskValidationError,
    validate_task_dict,
)

__all__ = [
    "Task",
    "ResourceLimits",
    "TaskValidationError",
    "validate_task_dict",
    "load_task",
    "parse_task_text",
    "discover_tasks",
    "discover_task_files",
    "find_task",
    "resolve_fixture",
    "fixture_exists",
    "check_fixture",
    "KNOWN_TOOLS",
    "SCORING_METHODS",
    "SCHEMA_VERSION",
    "SUPPORTED_VERSIONS",
    "DEFAULT_TIMEOUT_SECONDS",
]
