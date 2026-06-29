"""Policy enforcement: evaluate a tool call against a :class:`SandboxPolicy`.

:class:`Sandbox` is the runtime-facing object. It does two things, both *before*
and *after* a tool runs:

- :meth:`Sandbox.check_call` — a **pre-execution** decision. Given an agent's
  :class:`ToolCall` and the :class:`ToolContext` it would run in, it extracts the
  paths a path tool would touch (or the program an exec tool would run) and
  returns a :class:`PolicyDecision`. A denied call is **not** dispatched; the
  runtime records a structured "blocked" result instead.
- :meth:`Sandbox.redact_result` — a **post-execution** scrub. It runs the result's
  textual fields through the secret scanner so a captured secret never reaches a
  step record, a trace, or the agent's next observation.

The mapping from a tool name to *what it touches* is intentionally explicit and
small (the tool set is closed). Tools not listed here (``search_repo``,
``git_diff``) take no caller-supplied path and run a fixed, safe program, so the
path/command policy does not gate them beyond the workspace confinement the tools
already enforce; that is documented as a limitation, not a silent gap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..tools import ToolCall, ToolContext, ToolError, ToolResult
from ..tools._exec import normalize_argv
from ..tools.apply_patch import patch_target_paths
from .policy import NETWORK_PROGRAMS, SandboxPolicy
from .secret_scanner import REDACTABLE_TEXT_KEYS, redact_text

#: Path-taking tools → (argument name holding the path, access mode). Mirrors the
#: tool registry; a test asserts these names are real registered tools.
_PATH_TOOLS: dict[str, tuple[str, str]] = {
    "read_file": ("path", "read"),
    "write_file": ("path", "write"),
}
#: ``apply_patch`` is a write tool but its targets come from parsing the patch.
_PATCH_TOOL = "apply_patch"
#: Exec tools whose ``command`` argument is governed by the command/network policy.
_EXEC_TOOLS: dict[str, str] = {"run_shell": "command", "run_tests": "command"}


@dataclass(frozen=True)
class PolicyDecision:
    """The outcome of evaluating one tool call against the policy.

    ``rule`` is a short machine token (``"ok"``, ``"denied_path"``,
    ``"outside_workspace"``, ``"read_path_not_allowed"``,
    ``"write_path_not_allowed"``, ``"command_denylist"``,
    ``"command_not_allowlisted"``, ``"network_denied"``); ``reason`` is the
    human-readable explanation recorded in the blocked result and the trace.
    """

    allowed: bool
    rule: str
    reason: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "rule": self.rule,
            "reason": self.reason,
            "detail": dict(self.detail),
        }


def _allow(rule: str = "ok", reason: str = "permitted by policy", **detail: Any) -> PolicyDecision:
    return PolicyDecision(allowed=True, rule=rule, reason=reason, detail=detail)


def _deny(rule: str, reason: str, **detail: Any) -> PolicyDecision:
    return PolicyDecision(allowed=False, rule=rule, reason=reason, detail=detail)


def _program_name(argv0: str) -> str:
    """The bare program name of ``argv[0]`` (basename, no directory)."""
    return argv0.rsplit("/", 1)[-1]


def _path_matches(relpath: str, pattern: str) -> bool:
    """True if a workspace-relative POSIX path matches a deny/allow pattern.

    A pattern matches when any of these hold, which covers the shapes used in the
    default lists (exact files, basename globs like ``*.pem``, and directory names
    like ``.git`` / ``.aws`` appearing anywhere in the path):

    - the whole path matches the glob (``fnmatch``);
    - the path's basename matches the glob;
    - the pattern is a plain (wildcard-free) name equal to one of the path's
      segments — i.e. the path is that file or lives under that directory.
    """
    from fnmatch import fnmatch

    rel = relpath.strip("/")
    if fnmatch(rel, pattern):
        return True
    name = rel.rsplit("/", 1)[-1]
    if fnmatch(name, pattern):
        return True
    if not any(ch in pattern for ch in "*?[") and "/" not in pattern:
        return pattern in rel.split("/")
    return False


class Sandbox:
    """Enforce a :class:`SandboxPolicy`: gate tool calls and redact results."""

    def __init__(self, policy: SandboxPolicy) -> None:
        self.policy = policy

    # -- pre-execution gating ----------------------------------------------

    def check_call(self, call: ToolCall, ctx: ToolContext) -> PolicyDecision:
        """Decide whether ``call`` may run in ``ctx`` under this policy.

        Returns an *allow* decision for any tool whose arguments the policy does
        not govern (or cannot extract — e.g. a missing/mistyped argument), so the
        tool's own validation produces the error rather than the policy guessing.
        """
        args = dict(call.args)
        if call.tool in _PATH_TOOLS:
            arg_name, mode = _PATH_TOOLS[call.tool]
            raw = args.get(arg_name)
            if not isinstance(raw, str):
                return _allow()  # tool arg-validation will reject it
            return self._check_path(ctx, raw, mode)
        if call.tool == _PATCH_TOOL:
            patch = args.get("patch")
            if not isinstance(patch, str):
                return _allow()
            for target in patch_target_paths(patch):
                decision = self._check_path(ctx, target, "write")
                if not decision.allowed:
                    return decision
            return _allow()
        if call.tool in _EXEC_TOOLS:
            raw_cmd = args.get(_EXEC_TOOLS[call.tool])
            return self._check_command(raw_cmd)
        return _allow()

    def _check_path(self, ctx: ToolContext, raw: str, mode: str) -> PolicyDecision:
        try:
            resolved = ctx.resolve(raw)
        except ToolError as exc:
            # An out-of-workspace path is a policy denial with a clear rule (the
            # tool would also refuse it; we surface it earlier for the trace).
            return _deny("outside_workspace", str(exc), path=raw, mode=mode)
        rel = ctx.relpath(resolved) or "."

        for pattern in self.policy.denied_paths:
            if _path_matches(rel, pattern):
                return _deny(
                    "denied_path",
                    f"path {rel!r} matches a denied pattern ({pattern!r})",
                    path=rel,
                    pattern=pattern,
                    mode=mode,
                )

        allowed = (
            self.policy.allowed_read_paths if mode == "read" else self.policy.allowed_write_paths
        )
        if allowed is not None and not any(_path_matches(rel, p) for p in allowed):
            return _deny(
                f"{mode}_path_not_allowed",
                f"path {rel!r} is not in the allowed {mode} paths",
                path=rel,
                mode=mode,
            )
        return _allow(path=rel, mode=mode)

    def _check_command(self, raw_command: Any) -> PolicyDecision:
        if raw_command is None:
            # run_tests with no command uses its safe default (pytest); allow.
            return _allow()
        try:
            argv = normalize_argv(raw_command)
        except ToolError:
            return _allow()  # malformed command: let the tool report it
        program = _program_name(argv[0])

        if self.policy.command_allowlist is not None and program not in self.policy.command_allowlist:
            return _deny(
                "command_not_allowlisted",
                f"command {program!r} is not in the allowlist",
                program=program,
            )
        if program in self.policy.command_denylist:
            return _deny(
                "command_denylist",
                f"command {program!r} is on the denylist",
                program=program,
            )
        if not self.policy.network and program in NETWORK_PROGRAMS:
            return _deny(
                "network_denied",
                f"command {program!r} needs network access, which this policy denies",
                program=program,
            )
        return _allow(program=program)

    def blocked_result(self, call: ToolCall, decision: PolicyDecision) -> ToolResult:
        """Build the structured 'blocked' result recorded for a denied call.

        Shares the ``"blocked"`` category with ``allowed_tools`` gating so replay
        and reports treat both the same way; the policy rule lives in ``data``.
        """
        return ToolResult(
            tool=call.tool,
            category="blocked",
            ok=False,
            summary=f"blocked by sandbox policy: {decision.reason}",
            data={"policy_rule": decision.rule, **dict(decision.detail)},
            error=f"sandbox policy denied {call.tool!r}: {decision.reason}",
        )

    # -- post-execution redaction ------------------------------------------

    def redact_result(self, result: ToolResult) -> ToolResult:
        """Return ``result`` with credential-shaped output redacted.

        A no-op (returns the same object) when redaction is off or nothing
        matched, so an untouched result is not needlessly rebuilt. When something
        is redacted, ``data['redacted_secret_count']`` records how many.
        """
        if not self.policy.redact_secrets:
            return result

        total = 0
        new_data = dict(result.data)
        for key in REDACTABLE_TEXT_KEYS:
            value = new_data.get(key)
            if isinstance(value, str):
                cleaned, n = redact_text(value)
                if n:
                    new_data[key] = cleaned
                    total += n

        summary, n_summary = redact_text(result.summary)
        total += n_summary
        error = result.error
        if isinstance(error, str):
            error, n_error = redact_text(error)
            total += n_error

        if total == 0:
            return result
        new_data["redacted_secret_count"] = total
        return ToolResult(
            tool=result.tool,
            category=result.category,
            ok=result.ok,
            summary=summary or result.summary,
            data=new_data,
            error=error,
        )
