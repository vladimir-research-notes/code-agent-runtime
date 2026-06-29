"""The ``expected_files`` scorer (Milestone 8).

Pass iff the workspace matches a set of file expectations after the run. This
scores tasks where the right outcome is a filesystem state — a file created,
removed, or containing particular text — rather than a passing test suite.

``scoring_config`` keys (validated by the task schema; at least one required):

- ``present``: paths that must exist after the run.
- ``absent``: paths that must *not* exist.
- ``contains``: a list of ``{"path": ..., "text": ...}`` where ``text`` is a
  string or list of strings; the file must exist and contain every string.

Paths are workspace-relative; one that escapes the workspace fails its check
rather than reading outside it. The scorer reads the *live* workspace, so it must
run before the runtime cleans it up — which is exactly when the loop scores.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .scorer import CheckResult, ScoreInput, ScoreVerdict, from_checks, not_scored


def _resolve_in_workspace(workspace: Path, rel: str) -> Path | None:
    """Resolve ``rel`` under ``workspace``; ``None`` if it escapes the directory."""
    root = workspace.resolve()
    candidate = (root / rel).resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def score_expected_files(inp: ScoreInput) -> ScoreVerdict:
    """Score by checking the workspace's files against the configured expectations."""
    if inp.workspace is None:
        return not_scored(
            "expected_files",
            "the workspace is unavailable, so file expectations cannot be checked",
        )
    workspace = inp.workspace
    config = inp.config
    checks: list[CheckResult] = []

    for rel in config.get("present", []):
        resolved = _resolve_in_workspace(workspace, rel)
        if resolved is None:
            checks.append(CheckResult(f"present:{rel}", False, f"{rel!r} escapes the workspace"))
        else:
            ok = resolved.exists()
            checks.append(
                CheckResult(f"present:{rel}", ok, f"{rel!r} {'exists' if ok else 'is missing'}")
            )

    for rel in config.get("absent", []):
        resolved = _resolve_in_workspace(workspace, rel)
        if resolved is None:
            # An escaping path cannot exist in the workspace, so "absent" holds.
            checks.append(CheckResult(f"absent:{rel}", True, f"{rel!r} escapes the workspace (absent)"))
        else:
            ok = not resolved.exists()
            checks.append(
                CheckResult(f"absent:{rel}", ok, f"{rel!r} {'is absent' if ok else 'still exists'}")
            )

    for item in config.get("contains", []):
        checks.append(_check_contains(workspace, item))

    if not checks:  # pragma: no cover - schema requires at least one expectation
        return not_scored("expected_files", "no file expectations were declared")
    return from_checks("expected_files", tuple(checks), all_label="file expectation(s)")


def _check_contains(workspace: Path, item: Mapping[str, Any]) -> CheckResult:
    rel = item.get("path", "")
    raw_text = item.get("text", "")
    needles = [raw_text] if isinstance(raw_text, str) else list(raw_text)
    name = f"contains:{rel}"

    resolved = _resolve_in_workspace(workspace, rel)
    if resolved is None:
        return CheckResult(name, False, f"{rel!r} escapes the workspace")
    if not resolved.is_file():
        return CheckResult(name, False, f"{rel!r} is missing")
    content = _read_text(resolved)
    if content is None:
        return CheckResult(name, False, f"{rel!r} could not be read")
    missing = [n for n in needles if n not in content]
    if missing:
        shown = ", ".join(repr(n) for n in missing)
        return CheckResult(name, False, f"{rel!r} does not contain {shown}")
    return CheckResult(name, True, f"{rel!r} contains the expected text")
