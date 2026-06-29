"""Workspace preparation and tool gating for the runtime (Milestone 4).

This module owns the runtime's side effects on the host: it materialises a fresh,
disposable copy of a task's fixture (the *workspace*) that the agent's tools act
on, and it gates each agent tool call against the task's ``allowed_tools`` before
the registry dispatches it.

Two honesty notes:

- **The workspace is a copy, not a jail.** Tools are already confined to the
  workspace directory (Milestone 3), and preparing a clean copy means a run never
  mutates the committed fixture. But there is still **no** process isolation,
  resource limit, or network policy here — that is the sandbox in Milestone 7.
  Do not run untrusted tasks against a real host with this alone.
- **``allowed_tools`` gating is a capability check, not the full policy.** It
  refuses tools the task did not grant. Path/command/network policy and secret
  scanning are Milestone 7; this is the part of containment that belongs to the
  run loop and is cheap to do correctly now.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..tasks import Task, resolve_fixture
from ..tools import ToolCall, ToolContext, ToolRegistry, ToolResult

#: Directories/files never copied into a workspace (caches, vcs, virtualenvs).
_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".git", ".pytest_cache", ".venv", ".mypy_cache"
)


class WorkspaceError(RuntimeError):
    """Raised when a workspace cannot be prepared (missing/unsuitable fixture)."""


@dataclass(frozen=True)
class Workspace:
    """A prepared, disposable copy of a task's fixture.

    ``git`` records whether the copy was successfully initialised as a git repo
    (so the final diff can be captured); it is ``False`` when ``git`` is absent
    or initialisation failed, and the runtime degrades gracefully in that case.
    """

    root: Path
    fixture: Path
    git: bool

    def cleanup(self) -> None:
        """Remove the workspace directory (best effort; never raises)."""
        shutil.rmtree(self.root, ignore_errors=True)


def prepare_workspace(
    task: Task, *, dest: str | Path | None = None, init_git: bool = True
) -> Workspace:
    """Materialise ``task``'s fixture into a fresh workspace and return it.

    A directory fixture is copied (minus caches/vcs) into the workspace root so
    task-relative paths like ``summation.py`` resolve at the root. A single-file
    fixture is copied into an otherwise empty workspace. With ``init_git`` and a
    ``git`` binary present, the workspace is initialised and committed so
    :func:`capture_diff` can later report the agent's change set.
    """
    fixture = Path(resolve_fixture(task))
    if not fixture.exists():
        raise WorkspaceError(
            f"fixture for task {task.id!r} does not exist: {fixture}"
        )

    root = Path(dest) if dest is not None else Path(tempfile.mkdtemp(prefix="car-run-"))
    root.mkdir(parents=True, exist_ok=True)

    if fixture.is_dir():
        shutil.copytree(fixture, root, dirs_exist_ok=True, ignore=_COPY_IGNORE)
    else:
        shutil.copy2(fixture, root / fixture.name)

    git_ready = False
    if init_git and shutil.which("git") is not None:
        git_ready = _git_init_commit(root)
    return Workspace(root=root, fixture=fixture, git=git_ready)


def _git_init_commit(root: Path) -> bool:
    """Init a git repo in ``root`` and commit the fixture. Return success.

    Uses ``-c`` identity flags so the commit works without a configured global
    git identity. Any failure (no git, hooks, odd environment) returns ``False``
    rather than aborting the run — the diff is a nicety, not a requirement.
    """
    steps = (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        [
            "git",
            "-c",
            "user.email=runtime@code-agent-runtime.local",
            "-c",
            "user.name=code-agent-runtime",
            "commit",
            "-q",
            "-m",
            "fixture baseline",
        ],
    )
    try:
        for argv in steps:
            proc = subprocess.run(
                argv, cwd=str(root), capture_output=True, text=True, timeout=60
            )
            if proc.returncode != 0:
                return False
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def make_context(task: Task, workspace: Workspace, *, tool_timeout_seconds: int) -> ToolContext:
    """Build the :class:`ToolContext` tools run in for this workspace.

    The output bound honours the task's declared ``resource_limits.max_output_bytes``
    when set (otherwise the tool default); time is the configured per-tool budget.
    """
    limits = task.resource_limits
    kwargs: dict[str, int] = {"timeout_seconds": tool_timeout_seconds}
    if limits.max_output_bytes is not None:
        kwargs["max_output_bytes"] = limits.max_output_bytes
    return ToolContext.for_dir(workspace.root, **kwargs)


def dispatch_agent_call(
    registry: ToolRegistry,
    allowed_tools: Iterable[str],
    call: ToolCall,
    ctx: ToolContext,
) -> tuple[ToolResult, bool]:
    """Run an agent's ``call`` if the task allows the tool; otherwise block it.

    Returns ``(result, allowed)``. A blocked call yields a structured failed
    result (category ``"blocked"``) and ``allowed=False`` — recorded in the
    trace like any other step — and the tool is **not** executed.
    """
    allowed = set(allowed_tools)
    if call.tool not in allowed:
        result = ToolResult(
            tool=call.tool,
            category="blocked",
            ok=False,
            summary=f"blocked: {call.tool!r} is not in the task's allowed_tools",
            error=(
                f"tool {call.tool!r} is not permitted by this task "
                f"(allowed: {', '.join(sorted(allowed)) or 'none'})"
            ),
        )
        return result, False
    return registry.dispatch(call, ctx), True
