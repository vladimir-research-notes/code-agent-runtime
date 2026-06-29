"""Workspace preparation and tool gating for the runtime (Milestone 4).

This module owns the runtime's side effects on the host: it materialises a fresh,
disposable copy of a task's fixture (the *workspace*) that the agent's tools act
on, and it gates each agent tool call against the task's ``allowed_tools`` before
the registry dispatches it.

Two honesty notes:

- **The workspace is a copy, not a jail.** Tools are confined to the workspace
  directory (Milestone 3), and preparing a clean copy means a run never mutates
  the committed fixture. The Milestone 7 sandbox adds path/command/network policy
  and output/time caps on top, but there is still **no** process or namespace
  isolation here (a containerised runner is a documented non-goal for now). Do not
  run a deliberately malicious agent against a real host with this alone.
- **Gating has two layers.** :func:`dispatch_agent_call` first applies the task's
  ``allowed_tools`` capability check, then — when a :class:`~code_agent_runtime.sandbox.Sandbox`
  is supplied — the sandbox policy (allowed/denied paths, command allow/deny,
  network), and finally redacts the result's output through the secret scanner. A
  block at either layer is recorded as a structured ``"blocked"`` step.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..sandbox import Sandbox, SandboxPolicy
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


def make_context(
    task: Task,
    workspace: Workspace,
    *,
    tool_timeout_seconds: int,
    policy: SandboxPolicy | None = None,
) -> ToolContext:
    """Build the :class:`ToolContext` tools run in for this workspace.

    When a sandbox ``policy`` is given (Milestone 7), the per-command caps come
    from it: output is bounded by ``policy.max_output_bytes`` and the wall-clock
    budget is the *tighter* of the configured per-tool budget and
    ``policy.max_runtime_seconds`` — so a policy can lower a cap but never raise
    it above the run's configured ceiling. Without a policy, the legacy behaviour
    holds: the task's declared ``resource_limits.max_output_bytes`` (else the tool
    default) and the configured per-tool time budget.
    """
    if policy is not None:
        return ToolContext.for_dir(
            workspace.root,
            max_output_bytes=policy.max_output_bytes,
            timeout_seconds=min(tool_timeout_seconds, policy.max_runtime_seconds),
        )
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
    *,
    sandbox: Sandbox | None = None,
) -> tuple[ToolResult, bool]:
    """Run an agent's ``call`` if the task and sandbox allow it; else block it.

    Returns ``(result, allowed)``. A call is gated in two layers: first the task's
    ``allowed_tools`` capability check, then (when ``sandbox`` is given) the
    Milestone 7 policy — path/command/network rules. A block at either layer yields
    a structured failed result (category ``"blocked"``) and ``allowed=False``, and
    the tool is **not** executed. When a call is permitted and a ``sandbox`` is
    present, the tool's result is run through the secret scanner before it is
    returned, so a captured credential never reaches the step record, the trace,
    or the agent's next observation.
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
    if sandbox is not None:
        decision = sandbox.check_call(call, ctx)
        if not decision.allowed:
            return sandbox.blocked_result(call, decision), False
    result = registry.dispatch(call, ctx)
    if sandbox is not None:
        result = sandbox.redact_result(result)
    return result, True
