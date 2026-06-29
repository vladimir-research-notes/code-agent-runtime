"""Subprocess execution shared by the exec-category tools (Milestone 3).

A single, deliberately small wrapper around :mod:`subprocess` used by
``run_shell``, ``run_tests``, and ``git_diff``. It exists to centralise three
properties every command-running tool needs:

- **No shell.** Commands run with ``shell=False`` over an argv list. A string
  command is split with :func:`shlex.split`, so quoting works but shell
  metacharacters (pipes, redirects, ``&&``, globbing, ``$VAR``) are *not*
  interpreted. This is a conscious safety choice, not an oversight: enabling a
  shell would make command injection trivial. Tools that document a "shell
  command" therefore run a single program, not a shell pipeline.
- **Bounded output.** stdout and stderr are each truncated to
  ``max_output_bytes`` so a runaway command cannot blow up a result or trace.
- **Bounded time.** A timeout kills the process group and returns whatever was
  captured, flagged ``timed_out``.

Real process isolation (cgroups, namespaces, network policy) is **not** here;
that is the sandbox's job in Milestone 7. This wrapper only bounds output and
time and avoids a shell.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import ToolError


@dataclass(frozen=True)
class CompletedCommand:
    """Structured outcome of a single subprocess run."""

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    truncated: bool
    timed_out: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
            "timed_out": self.timed_out,
        }


def normalize_argv(command: str | list | tuple) -> tuple[str, ...]:
    """Turn a shell string or argv list into a validated argv tuple.

    A string is split with shell quoting rules (but never executed by a shell).
    Raises :class:`ToolError` on an empty or malformed command.
    """
    if isinstance(command, str):
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise ToolError(f"not a valid command string: {exc}") from exc
    elif isinstance(command, (list, tuple)):
        if not all(isinstance(part, str) for part in command):
            raise ToolError("command list must contain only strings")
        argv = list(command)
    else:  # pragma: no cover - guarded by tool arg validation
        raise ToolError(f"command must be a string or list, got {type(command).__name__}")
    if not argv:
        raise ToolError("command must not be empty")
    return tuple(argv)


def run_command(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> CompletedCommand:
    """Run ``argv`` in ``cwd`` with bounded time and output (no shell)."""
    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"command not found: {argv[0]!r}") from exc
    except OSError as exc:
        raise ToolError(f"could not start command {argv[0]!r}: {exc}") from exc

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        timed_out = True

    stdout, out_trunc = _bounded(out, max_output_bytes)
    stderr, err_trunc = _bounded(err, max_output_bytes)
    return CompletedCommand(
        argv=argv,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=out_trunc or err_trunc,
        timed_out=timed_out,
    )


def _bounded(raw: bytes | None, max_bytes: int) -> tuple[str, bool]:
    raw = raw or b""
    truncated = len(raw) > max_bytes
    return raw[:max_bytes].decode("utf-8", errors="replace"), truncated
