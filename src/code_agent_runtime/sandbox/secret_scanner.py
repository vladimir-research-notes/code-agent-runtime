"""Secret scanning and redaction for tool output (Milestone 7).

The trace recorder (Milestone 5) and the replay reports (Milestone 6) both noted
the same limitation: captured command output is stored *as captured*, so a trace
could contain whatever a command printed — including a secret. This module closes
that gap. When a policy has ``redact_secrets`` on, the sandbox runs every tool
result's textual fields (file contents, stdout/stderr, a diff) through
:func:`redact_text` before the result is recorded into a step, embedded in a
trace, or handed back to the agent as its next observation.

It reuses the **same** credential patterns as the repository hygiene scanner
(:data:`code_agent_runtime.hygiene.SECRET_PATTERNS`) so the commit-time guard and
the runtime redactor agree on what "looks like a secret" — one source of truth,
no drift. Detection is therefore heuristic and high-precision by design: it
catches common credential shapes (AWS keys, private-key blocks, provider API
keys, ``key = <long value>`` assignments) but is **not** a guarantee that no
secret can slip through, and it does not detect non-secret sensitive data. This
is recorded as a limitation, not a solved problem.
"""

from __future__ import annotations

from ..hygiene import SECRET_PATTERNS, _PLACEHOLDER

#: Result-data keys whose values are free text worth scanning. Other fields are
#: structured (ints, booleans, path lists) and are left untouched.
REDACTABLE_TEXT_KEYS: tuple[str, ...] = ("content", "stdout", "stderr", "diff")


def _redaction_token(name: str) -> str:
    return f"[redacted:{name}]"


def _is_placeholder_value(value: str) -> bool:
    """Mirror the hygiene scanner's filter for the generic-credential rule.

    A value that looks like a path, a version number, or an obvious placeholder
    is not treated as a real secret, so we neither flag nor redact it.
    """
    return bool(_PLACEHOLDER.match(value)) or "/" in value or value.count(".") >= 2


def redact_text(text: str | None) -> tuple[str | None, int]:
    """Replace credential-shaped substrings in ``text`` with a redaction token.

    Returns ``(redacted_text, count)``. ``None`` (e.g. a binary file's absent
    ``content``) and empty strings pass through with a zero count. Patterns are
    applied in the hygiene scanner's order (the heuristic generic-assignment rule
    last) so a specific high-precision match is preferred over the broad one.
    """
    if not text:
        return text, 0

    count = 0
    redacted = text
    for name, pattern in SECRET_PATTERNS:

        def _replace(match, _name: str = name) -> str:
            nonlocal count
            if _name == "generic_credential_assignment":
                value = match.group("value")
                if _is_placeholder_value(value):
                    return match.group(0)  # not a credential; leave as-is
                count += 1
                # Keep the key and the assignment, redact only the value.
                return match.group(0).replace(value, _redaction_token(_name), 1)
            count += 1
            return _redaction_token(_name)

        redacted = pattern.sub(_replace, redacted)
    return redacted, count


def count_secrets(text: str | None) -> int:
    """Number of credential-shaped substrings :func:`redact_text` would redact."""
    return redact_text(text)[1]
