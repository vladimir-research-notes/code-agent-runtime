"""Declarative sandbox policy (Milestone 7).

A :class:`SandboxPolicy` is the *intent* of containment expressed as data: which
workspace paths a tool may read or write, which paths are always off-limits,
which programs an exec tool may or may not run, whether the network is permitted,
and the per-command runtime / output caps. It is pure data — it executes nothing.
Enforcement is :mod:`.permissions` (which evaluates a tool call against a policy)
and the runtime loop (which builds the bounded :class:`ToolContext`); redaction is
:mod:`.secret_scanner`.

Honest framing (see ``docs/SECURITY_MODEL.md``): these controls reduce blast
radius and make actions observable for a *semi-trusted, deterministic* agent on a
developer machine. They are **not** a jail. In particular:

- **Path policy** is layered on top of the tools' existing workspace confinement
  (a tool already refuses to touch anything outside its workspace). The policy
  adds finer rules *inside* the workspace — denying sensitive files like ``.env``
  and restricting writes — and reclassifies an out-of-workspace path as a policy
  denial for a clearer trace.
- **Command policy** matches the *program name* (``argv[0]`` basename) against an
  allow/deny list. Commands run with no shell, so metacharacters are not a path
  to injection, but a denied program name is a coarse signal: a program renamed or
  invoked by an absolute path to a copy is not caught. It is a guardrail, not a
  sandbox.
- **Network policy** is enforced *heuristically* by denying well-known network
  programs (``curl``, ``wget``, ``ssh``, ...) when network is off. A program that
  opens a socket directly (e.g. ``python3 -c "import socket; ..."``) is **not**
  blocked. True network isolation needs a container/namespace and is a non-goal
  here.
- **Runtime / output caps** are wall-clock and byte bounds applied through the
  :class:`ToolContext`; ``cpu_seconds`` from a task's ``resource_limits`` is used
  as the wall-clock bound when present (we do not enforce true CPU-time limits).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..tools.base import DEFAULT_MAX_OUTPUT_BYTES, DEFAULT_TOOL_TIMEOUT_SECONDS

if TYPE_CHECKING:  # avoid importing the tasks package at module load
    from ..tasks import Task

#: Default per-command wall-clock budget (seconds), mirroring the tools' default.
DEFAULT_MAX_RUNTIME_SECONDS = DEFAULT_TOOL_TIMEOUT_SECONDS

#: Workspace-relative path patterns that are always off-limits, even though they
#: live inside the workspace. Matched by :func:`permissions._path_matches`
#: (exact path, basename glob, or a directory name appearing as a path segment).
#: These protect developer secrets and VCS internals that a fixture might carry.
DEFAULT_DENIED_PATHS: tuple[str, ...] = (
    ".env",
    ".env.*",
    ".git",
    ".aws",
    ".ssh",
    ".gnupg",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.secret",
)

#: Program basenames an exec tool (``run_shell`` / ``run_tests``) may never run.
#: Deliberately limited to clearly host-destructive / privilege commands so that
#: ordinary build/test programs (``python3``, ``pytest``, ``node``, ...) still
#: work out of the box. Network programs are governed by :attr:`SandboxPolicy.network`
#: instead, so a task that opts into the network can still use them.
DEFAULT_COMMAND_DENYLIST: tuple[str, ...] = (
    "rm",
    "rmdir",
    "shred",
    "dd",
    "mkfs",
    "sudo",
    "su",
    "doas",
    "chmod",
    "chown",
    "chgrp",
    "mount",
    "umount",
    "kill",
    "killall",
    "pkill",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "crontab",
    "iptables",
    "nft",
)

#: Program basenames treated as network egress; denied when ``network`` is off.
NETWORK_PROGRAMS: frozenset[str] = frozenset(
    {
        "curl",
        "wget",
        "nc",
        "ncat",
        "netcat",
        "telnet",
        "ssh",
        "scp",
        "sftp",
        "ftp",
        "rsync",
        "socat",
    }
)


def _as_tuple(value: Sequence[str] | None) -> tuple[str, ...] | None:
    """Normalise an optional pattern sequence to a tuple (preserving ``None``)."""
    if value is None:
        return None
    return tuple(value)


@dataclass(frozen=True)
class SandboxPolicy:
    """A declarative containment policy for one run.

    ``allowed_read_paths`` / ``allowed_write_paths`` are workspace-relative glob
    patterns; ``None`` means "anywhere in the workspace" (the baseline workspace
    confinement still applies). ``denied_paths`` always wins over an allow rule.
    ``command_allowlist`` of ``None`` means "any program except the denylist".
    """

    allowed_read_paths: tuple[str, ...] | None = None
    allowed_write_paths: tuple[str, ...] | None = None
    denied_paths: tuple[str, ...] = DEFAULT_DENIED_PATHS
    command_allowlist: tuple[str, ...] | None = None
    command_denylist: tuple[str, ...] = DEFAULT_COMMAND_DENYLIST
    network: bool = False
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    redact_secrets: bool = True

    def __post_init__(self) -> None:
        # Normalise list/None fields to tuples so the policy is hashable, frozen,
        # and JSON-stable regardless of how a caller passed them.
        object.__setattr__(self, "allowed_read_paths", _as_tuple(self.allowed_read_paths))
        object.__setattr__(self, "allowed_write_paths", _as_tuple(self.allowed_write_paths))
        object.__setattr__(self, "denied_paths", tuple(self.denied_paths))
        object.__setattr__(self, "command_allowlist", _as_tuple(self.command_allowlist))
        object.__setattr__(self, "command_denylist", tuple(self.command_denylist))

    @classmethod
    def from_task(cls, task: Task) -> SandboxPolicy:
        """Build the default policy for ``task`` from its ``resource_limits``.

        The path and command rules use the safe defaults above; the network flag,
        output cap, and runtime cap are taken from the task's declared
        ``resource_limits`` when set (``cpu_seconds`` is used as the wall-clock
        runtime bound — see the module docstring).
        """
        limits = task.resource_limits
        kwargs: dict[str, Any] = {"network": limits.network}
        if limits.max_output_bytes is not None:
            kwargs["max_output_bytes"] = limits.max_output_bytes
        if limits.cpu_seconds is not None:
            kwargs["max_runtime_seconds"] = limits.cpu_seconds
        return cls(**kwargs)

    def summary_line(self) -> str:
        """A one-line, human-readable description for the run report."""
        read = "any" if self.allowed_read_paths is None else f"{len(self.allowed_read_paths)} glob(s)"
        write = (
            "any" if self.allowed_write_paths is None else f"{len(self.allowed_write_paths)} glob(s)"
        )
        cmds = "any" if self.command_allowlist is None else f"{len(self.command_allowlist)} allowed"
        return (
            f"read={read}, write={write}, denied={len(self.denied_paths)} path glob(s); "
            f"commands={cmds}, denylist={len(self.command_denylist)}; "
            f"network={'on' if self.network else 'off'}; "
            f"caps={self.max_runtime_seconds}s/{self.max_output_bytes}B; "
            f"redact={'on' if self.redact_secrets else 'off'}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict (lists, not tuples)."""
        return {
            "allowed_read_paths": (
                list(self.allowed_read_paths) if self.allowed_read_paths is not None else None
            ),
            "allowed_write_paths": (
                list(self.allowed_write_paths) if self.allowed_write_paths is not None else None
            ),
            "denied_paths": list(self.denied_paths),
            "command_allowlist": (
                list(self.command_allowlist) if self.command_allowlist is not None else None
            ),
            "command_denylist": list(self.command_denylist),
            "network": self.network,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_output_bytes": self.max_output_bytes,
            "redact_secrets": self.redact_secrets,
        }
