"""``apply_patch`` — apply a unified diff to the workspace (Milestone 3).

A small, dependency-free unified-diff applier. It deliberately does **not** shell
out to ``git apply``/``patch``: a pure-Python implementation is deterministic,
works in a non-git workspace, and is unit-testable without external binaries.

Supported: standard unified diffs over one or more files — file modification,
file creation (``--- /dev/null``), and file deletion (``+++ /dev/null``), with
``a/``/``b/`` path prefixes and the ``\\ No newline at end of file`` marker.

Out of scope (documented limitations, not silent behaviour): fuzzy/offset
matching (context must match exactly, or the whole patch is rejected), binary
patches, and rename/copy detection. Application is **atomic**: every file is
computed in memory first, and nothing is written unless all hunks apply cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)  # (tag, text); tag in ' -+'
    new_no_newline: bool = False

    @property
    def old_block(self) -> list[str]:
        return [text for tag, text in self.lines if tag in " -"]

    @property
    def new_block(self) -> list[str]:
        return [text for tag, text in self.lines if tag in " +"]


@dataclass
class FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def mode(self) -> str:
        if self.old_path is None:
            return "create"
        if self.new_path is None:
            return "delete"
        return "modify"

    @property
    def target(self) -> str:
        path = self.new_path if self.mode != "delete" else self.old_path
        assert path is not None  # mode invariants guarantee this
        return path

    @property
    def insertions(self) -> int:
        return sum(tag == "+" for h in self.hunks for tag, _ in h.lines)

    @property
    def deletions(self) -> int:
        return sum(tag == "-" for h in self.hunks for tag, _ in h.lines)


class ApplyPatchTool(Tool):
    """Apply a unified-diff patch to files in the workspace, atomically."""

    name = "apply_patch"
    category = "write"
    summary = "Apply a unified-diff patch to the workspace (create/modify/delete files)."
    params = (
        ToolParam("patch", "str", required=True, description="A unified-diff patch to apply."),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        patch_text = args["patch"]
        file_patches = _parse_unified_diff(patch_text)
        if not file_patches:
            raise ToolError("no file sections found in patch (expected '--- '/'+++ ' headers)")

        # Plan every change in memory first so a mismatch leaves the tree untouched.
        planned: list[tuple[Any, FilePatch, str | None]] = []
        for fp in file_patches:
            resolved = ctx.resolve(fp.target)
            if fp.mode == "create":
                if resolved.exists():
                    raise ToolError(f"cannot create {fp.target!r}: file already exists")
                original = None
            else:
                if not resolved.exists():
                    raise ToolError(f"cannot {fp.mode} {fp.target!r}: file does not exist")
                if not resolved.is_file():
                    raise ToolError(f"cannot {fp.mode} {fp.target!r}: not a regular file")
                original = resolved.read_text(encoding="utf-8")
            new_text = _apply_file_patch(original, fp)
            planned.append((resolved, fp, None if fp.mode == "delete" else new_text))

        # Commit.
        changed: list[dict[str, Any]] = []
        for resolved, fp, new_text in planned:
            if fp.mode == "delete":
                resolved.unlink()
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_text(new_text or "", encoding="utf-8")
            changed.append(
                {
                    "path": ctx.relpath(resolved),
                    "mode": fp.mode,
                    "hunks": len(fp.hunks),
                    "insertions": fp.insertions,
                    "deletions": fp.deletions,
                }
            )

        ins = sum(c["insertions"] for c in changed)
        dels = sum(c["deletions"] for c in changed)
        return self._ok(
            f"applied patch to {len(changed)} file(s), +{ins}/-{dels}",
            files=changed,
            files_changed=len(changed),
            insertions=ins,
            deletions=dels,
        )


# --- parsing ---------------------------------------------------------------


def _strip_prefix(path: str) -> str | None:
    """Normalise a diff header path: drop a tab-timestamp, ``a/``/``b/``, dev-null."""
    path = path.split("\t", 1)[0].strip()
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _parse_unified_diff(text: str) -> list[FilePatch]:
    lines = text.splitlines()
    i = 0
    n = len(lines)
    patches: list[FilePatch] = []
    while i < n:
        line = lines[i]
        if not line.startswith("--- "):
            i += 1  # skip 'diff --git', 'index', mode lines, and any preamble
            continue
        if i + 1 >= n or not lines[i + 1].startswith("+++ "):
            raise ToolError(f"malformed patch: '--- ' header not followed by '+++ ' (line {i + 1})")
        old_path = _strip_prefix(line[4:])
        new_path = _strip_prefix(lines[i + 1][4:])
        fp = FilePatch(old_path=old_path, new_path=new_path)
        i += 2
        # Read hunks for this file.
        while i < n and lines[i].startswith("@@"):
            hunk, i = _parse_hunk(lines, i)
            fp.hunks.append(hunk)
        if not fp.hunks:
            raise ToolError(f"file section for {fp.target!r} has no @@ hunks")
        patches.append(fp)
    return patches


def _parse_hunk(lines: list[str], i: int) -> tuple[Hunk, int]:
    m = _HUNK_RE.match(lines[i])
    if not m:
        raise ToolError(f"malformed hunk header: {lines[i]!r}")
    old_start = int(m.group(1))
    old_count = int(m.group(2)) if m.group(2) is not None else 1
    new_count = int(m.group(4)) if m.group(4) is not None else 1
    hunk = Hunk(old_start=old_start, old_count=old_count, new_count=new_count)
    i += 1
    seen_old = seen_new = 0
    n = len(lines)
    while i < n and (seen_old < old_count or seen_new < new_count):
        body = lines[i]
        if body == "":  # a blank context line emitted without the leading space
            hunk.lines.append((" ", ""))
            seen_old += 1
            seen_new += 1
        elif body[0] == " ":
            hunk.lines.append((" ", body[1:]))
            seen_old += 1
            seen_new += 1
        elif body[0] == "-":
            hunk.lines.append(("-", body[1:]))
            seen_old += 1
        elif body[0] == "+":
            hunk.lines.append(("+", body[1:]))
            seen_new += 1
        elif body[0] == "\\":  # "\ No newline at end of file"
            if hunk.lines and hunk.lines[-1][0] in " +":
                hunk.new_no_newline = True
        else:  # next hunk/file header or stray line ends the body
            break
        i += 1
    # Consume a trailing no-newline marker that follows the counted lines.
    if i < n and lines[i].startswith("\\"):
        if hunk.lines and hunk.lines[-1][0] in " +":
            hunk.new_no_newline = True
        i += 1
    return hunk, i


# --- application -----------------------------------------------------------


def _apply_file_patch(original: str | None, fp: FilePatch) -> str:
    """Return the new file text after applying ``fp``'s hunks to ``original``.

    Raises :class:`ToolError` if any hunk's context does not match exactly.
    """
    had_final_nl = bool(original) and original.endswith("\n")
    work: list[str] = original.splitlines() if original else []

    offset = 0
    for hunk in fp.hunks:
        old_block = hunk.old_block
        if old_block:
            start = hunk.old_start - 1 + offset
        else:  # pure insertion: old_start is the line to insert after (0-based)
            start = hunk.old_start + offset
        end = start + len(old_block)
        if start < 0 or end > len(work) or work[start:end] != old_block:
            raise ToolError(
                f"patch context does not match in {fp.target!r} "
                f"at @@ -{hunk.old_start} (file changed or wrong base)"
            )
        work[start:end] = hunk.new_block
        offset += len(hunk.new_block) - len(old_block)

    # Trailing-newline policy: an explicit "\ No newline" marker on the new side
    # wins; otherwise preserve the original's state, and treat a newly created
    # non-empty file as newline-terminated (the POSIX text convention).
    if any(h.new_no_newline for h in fp.hunks):
        add_newline = False
    else:
        add_newline = had_final_nl or original is None
    text = "\n".join(work)
    if work and add_newline:
        text += "\n"
    return text
