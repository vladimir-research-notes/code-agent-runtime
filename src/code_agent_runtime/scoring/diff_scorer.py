"""The ``diff_constraint`` scorer (Milestone 8).

Pass iff the agent's change stayed *within a declared file scope*. This is a
**constraint** scorer, not an achievement scorer: it answers "did the agent only
touch what it was allowed to?" — useful for refactors and scoped edits where
collateral changes are the failure mode — and is best paired with a correctness
check (combine the two via a ``custom`` scorer; see :mod:`.custom`).

``scoring_config`` keys (validated by the task schema):

- ``allowed_paths`` (required): glob patterns the change may touch. Every changed
  path must match at least one.
- ``forbidden_paths`` (optional): patterns that must *not* be touched (checked
  even if they would match ``allowed_paths``).
- ``max_files`` (optional): cap on the number of changed files.
- ``allow_empty`` (optional, default ``False``): when false, a run that changed
  nothing fails — so an agent that did nothing does not trivially "stay in
  scope".

Patterns are matched against the workspace-relative POSIX path and its basename
with :func:`fnmatch.fnmatch` (so ``*`` spans directory separators); e.g.
``summation.py``, ``src/*.py``, and ``*.py`` all behave as expected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fnmatch import fnmatch
from typing import Any

from .scorer import CheckResult, ScoreInput, ScoreVerdict, failed, not_scored, passed

#: Build artifacts ignored by diff-scope analysis: they are produced by running
#: tests/tools, not authored by the agent, so counting them as "out of scope"
#: would be noise. Mirrors the runtime's workspace ``_COPY_IGNORE`` and the repo
#: ``.gitignore``; documented as a limitation on the website.
DEFAULT_IGNORED_PATHS: tuple[str, ...] = (
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache",
)


def changed_paths(
    diff: Mapping[str, Any], *, ignore: Sequence[str] = DEFAULT_IGNORED_PATHS
) -> list[str]:
    """All workspace-relative paths the diff touched (tracked + new files).

    Paths matching ``ignore`` (default: Python bytecode caches) are dropped, so a
    ``.pyc`` written by the test run is not mistaken for an out-of-scope change.
    Pass ``ignore=()`` to include everything.
    """
    tracked = [f["path"] for f in diff.get("files", []) if "path" in f]
    untracked = list(diff.get("untracked", []))
    paths = sorted(set(tracked) | set(untracked))
    if ignore:
        paths = [p for p in paths if not matches_any(p, ignore)]
    return paths


def matches_any(relpath: str, patterns: Sequence[str]) -> bool:
    """True if ``relpath`` (or its basename) matches any glob in ``patterns``."""
    rel = relpath.strip("/")
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch(rel, p) or fnmatch(name, p) for p in patterns)


def score_diff_constraint(inp: ScoreInput) -> ScoreVerdict:
    """Score by whether the captured diff stayed within the configured scope."""
    if inp.diff is None:
        return not_scored(
            "diff_constraint",
            "no diff was captured, so the change scope cannot be evaluated "
            "(the workspace is not a git repository)",
        )

    config = inp.config
    allowed = list(config.get("allowed_paths", []))
    forbidden = list(config.get("forbidden_paths", []))
    max_files = config.get("max_files")
    allow_empty = bool(config.get("allow_empty", False))

    changed = changed_paths(inp.diff)
    checks: list[CheckResult] = []

    # Non-empty change (unless explicitly allowed) -------------------------
    if not changed and not allow_empty:
        return failed(
            "diff_constraint",
            "no files were changed (set scoring_config.allow_empty to permit this)",
            extra={"changed": []},
        )

    # Every changed path must be in scope ---------------------------------
    out_of_scope = [p for p in changed if not matches_any(p, allowed)]
    checks.append(
        CheckResult(
            name="within_allowed_paths",
            passed=not out_of_scope,
            detail=(
                "all changed paths are within allowed_paths"
                if not out_of_scope
                else f"changed paths outside scope: {', '.join(out_of_scope)}"
            ),
        )
    )

    # No forbidden path touched -------------------------------------------
    if forbidden:
        hit = [p for p in changed if matches_any(p, forbidden)]
        checks.append(
            CheckResult(
                name="no_forbidden_paths",
                passed=not hit,
                detail=(
                    "no forbidden paths were touched"
                    if not hit
                    else f"forbidden paths touched: {', '.join(hit)}"
                ),
            )
        )

    # File-count cap ------------------------------------------------------
    if max_files is not None:
        within = len(changed) <= max_files
        checks.append(
            CheckResult(
                name="within_max_files",
                passed=within,
                detail=(
                    f"changed {len(changed)} file(s), within the cap of {max_files}"
                    if within
                    else f"changed {len(changed)} file(s), over the cap of {max_files}"
                ),
            )
        )

    checks_t = tuple(checks)
    n_pass = sum(1 for c in checks_t if c.passed)
    extra = {"changed": changed, "out_of_scope": out_of_scope}
    if n_pass == len(checks_t):
        return passed(
            "diff_constraint",
            f"change stayed within scope ({len(changed)} file(s) changed)",
            checks_t,
            **extra,
        )
    failures = "; ".join(c.detail for c in checks_t if not c.passed)
    return failed("diff_constraint", f"change violated scope — {failures}", checks_t, **extra)
