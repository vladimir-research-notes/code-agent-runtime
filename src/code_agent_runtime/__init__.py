"""Code Agent Runtime.

A local-first runtime for running, tracing, sandboxing, replaying, and
evaluating coding agents under controlled conditions.

This top-level package currently exposes only version metadata and a small
CLI. The runtime, tracing, sandboxing, scoring, and adapter subpackages are
introduced milestone by milestone (see ``docs/PLAN.md``).
"""

from __future__ import annotations

__all__ = ["__version__", "PROJECT_NAME", "PROJECT_SUMMARY"]

#: Semantic version of the runtime. Stays at 0.x during the scaffold phase.
__version__ = "0.0.0"

#: Human-readable project name.
PROJECT_NAME = "Code Agent Runtime"

#: One-line description, kept in sync with ``pyproject.toml``.
PROJECT_SUMMARY = (
    "Local-first runtime for running, tracing, sandboxing, replaying, and "
    "evaluating coding agents under controlled conditions."
)
