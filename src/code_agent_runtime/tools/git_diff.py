"""``git_diff`` — capture the workspace's change set via git (Milestone 3).

This is how a run records *what the agent changed*. It shells to ``git`` (no
shell; argv only) inside the workspace and returns the unified diff plus a parsed
per-file insertion/deletion summary and the list of untracked files (new files
git does not yet track). It is read-category: it observes, it never mutates.

The workspace must be a git repository. The runtime (Milestone 4) initialises one
when it prepares a workspace; for direct use, ``git init`` the directory first. A
non-repo or a missing ``git`` binary yields a structured failure, not a crash.
"""

from __future__ import annotations

from typing import Any

from ._exec import run_command
from .base import Tool, ToolContext, ToolError, ToolParam, ToolResult


class GitDiffTool(Tool):
    """Return the working-tree (or staged) diff of the workspace git repo."""

    name = "git_diff"
    category = "read"
    summary = "Capture the workspace's git diff and a per-file change summary."
    params = (
        ToolParam(
            "staged",
            "bool",
            required=False,
            description="Diff the staged index instead of the working tree (default: false).",
            default=False,
        ),
        ToolParam(
            "paths",
            "str|list",
            required=False,
            description="Limit the diff to these workspace-relative path(s).",
        ),
    )

    def _run(self, ctx: ToolContext, **args: Any) -> ToolResult:
        staged = args.get("staged", False)
        paths = self._normalize_paths(ctx, args.get("paths"))
        self._require_git_repo(ctx)

        base = ["git", "diff", "--no-color"]
        if staged:
            base.append("--cached")
        pathspec = (["--", *paths]) if paths else []

        diff = self._git(ctx, base + pathspec)
        numstat = self._git(ctx, base + ["--numstat"] + pathspec)
        files, insertions, deletions = _parse_numstat(numstat.stdout)
        untracked = self._untracked(ctx)

        changed = len(files) + (len(untracked) if not staged else 0)
        summary = (
            f"{changed} file(s) changed, +{insertions}/-{deletions}"
            + (" (staged)" if staged else "")
            + (" [truncated]" if diff.truncated else "")
        )
        return self._ok(
            summary,
            is_git_repo=True,
            staged=staged,
            diff=diff.stdout,
            files=files,
            insertions=insertions,
            deletions=deletions,
            untracked=untracked,
            truncated=diff.truncated,
        )

    # -- helpers ------------------------------------------------------------

    def _git(self, ctx: ToolContext, argv: list[str]):
        return run_command(
            tuple(argv),
            cwd=ctx.workspace,
            timeout_seconds=ctx.timeout_seconds,
            max_output_bytes=ctx.max_output_bytes,
        )

    def _require_git_repo(self, ctx: ToolContext) -> None:
        probe = self._git(ctx, ["git", "rev-parse", "--is-inside-work-tree"])
        if probe.exit_code != 0 or probe.stdout.strip() != "true":
            raise ToolError(
                f"workspace is not a git repository: {ctx.workspace} "
                "(run `git init` or let the runtime prepare the workspace)"
            )

    def _untracked(self, ctx: ToolContext) -> list[str]:
        status = self._git(ctx, ["git", "status", "--porcelain", "--untracked-files=all"])
        out: list[str] = []
        for line in status.stdout.splitlines():
            if line.startswith("?? "):
                out.append(line[3:].strip())
        return sorted(out)

    @staticmethod
    def _normalize_paths(ctx: ToolContext, raw: Any) -> list[str]:
        if raw is None:
            return []
        items = [raw] if isinstance(raw, str) else list(raw)
        rels: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ToolError("'paths' must be a string or list of strings")
            # Confine to the workspace, then express relative to it for git.
            rels.append(ctx.relpath(ctx.resolve(item)))
        return rels


def _parse_numstat(text: str) -> tuple[list[dict[str, Any]], int, int]:
    """Parse ``git diff --numstat`` output into per-file counts and totals.

    Binary files report ``-`` for both counts; we record them with ``None``
    insertions/deletions and exclude them from the numeric totals.
    """
    files: list[dict[str, Any]] = []
    total_ins = 0
    total_del = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins_s, del_s, path = parts[0], parts[1], "\t".join(parts[2:])
        if ins_s == "-" or del_s == "-":
            files.append({"path": path, "insertions": None, "deletions": None, "binary": True})
            continue
        try:
            ins, dels = int(ins_s), int(del_s)
        except ValueError:  # pragma: no cover - defensive against odd output
            continue
        files.append({"path": path, "insertions": ins, "deletions": dels, "binary": False})
        total_ins += ins
        total_del += dels
    return files, total_ins, total_del
