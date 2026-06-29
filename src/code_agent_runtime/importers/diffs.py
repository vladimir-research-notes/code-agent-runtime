"""Diff helpers for the importer (Milestone 11).

The importer has to produce the **same** diff shape the runtime's ``git_diff``
tool produces — a per-file ``insertions``/``deletions`` summary plus the unified
text — so the imported run can flow through the existing scorers and reports
unchanged (``diff_constraint`` reads ``files[].path`` and ``untracked``; the
reports read the counts). It does so two ways, depending on what the source
gave us:

- :func:`tree_diff` — when we hold both the before and after *content* (a
  before/after directory pair, or a synthetic run's snapshot), it computes an
  exact unified diff with :mod:`difflib` and counts the changed lines itself.
- :func:`parse_unified_diff` — when the source gave us only a unified diff *text*
  (a "diff + command log" import), it parses that text into the same shape.

Both are pure and dependency-free (no ``git`` binary): the importer must work on
a record exported elsewhere, where a workspace and git history may be long gone.

Honest limitation: a unified diff and ``git diff --numstat`` count lines the same
way for ordinary text changes, but a diff produced by a different tool (different
context size, rename detection, binary handling) may differ in detail. The counts
here are therefore *best-effort reconstructions*, accurate for the line-oriented
text changes these tasks involve and documented as approximate for anything
exotic. The high-signal path is verification (re-running the test command), which
does not depend on these counts at all.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _file_entry(path: str, insertions: int, deletions: int) -> dict[str, Any]:
    return {"path": path, "insertions": insertions, "deletions": deletions, "binary": False}


def tree_diff(
    before: Mapping[str, str | None], after: Mapping[str, str | None]
) -> dict[str, Any]:
    """Build a ``git_diff``-shaped dict from before/after content maps.

    ``before``/``after`` map a workspace-relative POSIX path to its full text
    content (``None`` means absent). The result mirrors
    :class:`~code_agent_runtime.tools.git_diff.GitDiffTool` output: a ``files``
    list of ``{path, insertions, deletions, binary}``, the totals, an empty
    ``untracked`` (added files are folded into ``files``, as a committed diff
    would show them), the combined unified ``diff`` text, and ``truncated``.
    """
    paths = sorted(set(before) | set(after))
    files: list[dict[str, Any]] = []
    total_ins = 0
    total_del = 0
    chunks: list[str] = []

    for path in paths:
        b = before.get(path)
        a = after.get(path)
        if (b or "") == (a or "") and (b is None) == (a is None):
            continue  # unchanged
        b_lines = _lines(b) if b is not None else []
        a_lines = _lines(a) if a is not None else []
        if b is None:  # added file: every line is an insertion
            ins, dels = len(a_lines), 0
        elif a is None:  # deleted file: every line is a deletion
            ins, dels = 0, len(b_lines)
        else:  # modified file: count the changed lines
            ins, dels = _count_changed_lines(b_lines, a_lines)
        from_label = f"a/{path}" if b is not None else "/dev/null"
        to_label = f"b/{path}" if a is not None else "/dev/null"
        chunk = "".join(
            difflib.unified_diff(b_lines, a_lines, fromfile=from_label, tofile=to_label)
        )
        if chunk and not chunk.endswith("\n"):
            chunk += "\n"
        chunks.append(f"diff --git a/{path} b/{path}\n{chunk}")
        files.append(_file_entry(path, ins, dels))
        total_ins += ins
        total_del += dels

    return {
        "is_git_repo": True,
        "staged": False,
        "diff": "".join(chunks),
        "files": files,
        "insertions": total_ins,
        "deletions": total_del,
        "untracked": [],
        "truncated": False,
    }


def _count_changed_lines(before: list[str], after: list[str]) -> tuple[int, int]:
    """Count inserted/deleted lines between two line lists (like ``--numstat``)."""
    ins = 0
    dels = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after).get_opcodes():
        if tag == "replace":
            dels += i2 - i1
            ins += j2 - j1
        elif tag == "delete":
            dels += i2 - i1
        elif tag == "insert":
            ins += j2 - j1
    return ins, dels


def _strip_ab_prefix(path: str) -> str:
    """Drop a leading ``a/`` or ``b/`` git diff prefix from a header path."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_unified_diff(text: str) -> dict[str, Any]:
    """Parse a unified diff *text* into a ``git_diff``-shaped dict.

    Recognises ``diff --git``, ``--- ``/``+++ `` file headers, ``new file``/``deleted
    file`` markers, and ``@@`` hunks; counts ``+``/``-`` body lines per file
    (excluding the ``+++``/``---`` headers). A file whose old side is ``/dev/null``
    is treated as added and listed under ``untracked`` (mirroring how ``git_diff``
    surfaces an as-yet-uncommitted new file). Robust to a missing trailing newline
    and to plain (non-``diff --git``) hunks.
    """
    files: list[dict[str, Any]] = []
    untracked: list[str] = []
    cur_path: str | None = None
    cur_ins = 0
    cur_del = 0
    cur_added = False  # old side is /dev/null
    saw_hunk = False

    def flush() -> None:
        nonlocal cur_path, cur_ins, cur_del, cur_added, saw_hunk
        if cur_path is not None and (saw_hunk or cur_ins or cur_del):
            files.append(_file_entry(cur_path, cur_ins, cur_del))
            if cur_added:
                untracked.append(cur_path)
        cur_path = None
        cur_ins = cur_del = 0
        cur_added = False
        saw_hunk = False

    for line in text.splitlines():
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            if len(parts) >= 4:
                cur_path = _strip_ab_prefix(parts[2])
            continue
        if line.startswith("--- "):
            target = line[4:].strip()
            if target in ("/dev/null", ""):
                cur_added = True
            elif cur_path is None:
                cur_path = _strip_ab_prefix(target)
            continue
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target not in ("/dev/null", "") and (cur_path is None or cur_path == "/dev/null"):
                cur_path = _strip_ab_prefix(target)
            continue
        if line.startswith("new file"):
            cur_added = True
            continue
        if line.startswith("@@"):
            saw_hunk = True
            continue
        if line.startswith("+"):
            cur_ins += 1
        elif line.startswith("-"):
            cur_del += 1
    flush()

    total_ins = sum(f["insertions"] for f in files)
    total_del = sum(f["deletions"] for f in files)
    # An added file's content already counts toward `files`; keep it there *and*
    # surface it under `untracked` so diff-scope scoring sees the new path.
    return {
        "is_git_repo": True,
        "staged": False,
        "diff": text if text.endswith("\n") or not text else text + "\n",
        "files": files,
        "insertions": total_ins,
        "deletions": total_del,
        "untracked": sorted(set(untracked)),
        "truncated": False,
    }
