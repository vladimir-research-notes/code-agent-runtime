"""Building an :class:`ImportedRun` from each external input form (Milestone 11).

The plan names four shapes a Claude-Code-like run can reach us in. This module
normalises each into the one :class:`ImportedRun` the converter and scorer
understand:

- :func:`import_before_after` — two directory snapshots (the workspace before and
  after the external agent ran). The richest source: it yields both the diff and
  the full after-state, so the run can be *verified*.
- :func:`import_diff_and_log` — a unified diff plus a command log (argv + exit
  codes). Carries the change and a declared test outcome, but no file content.
- :func:`import_transcript` — a manually exported transcript (a list of turns with
  optional tool uses). Carries the process; the change/outcome only if the
  transcript happened to record them.
- :func:`synthesize_import` — a deterministic, **offline** synthetic run this
  runtime generates by replaying a built-in scripted solution and snapshotting the
  result. This is the "synthetic Claude-Code-like trace" the milestone validates
  against, and the basis for the round-trip test (a native run, exported and
  re-imported, scores identically).

:func:`export_run` underlies the synthetic path: it turns any
:class:`~code_agent_runtime.runtime.state.RunResult` into an
:class:`ImportedRun`, which is how a real run becomes an importable record.
:func:`load_import_source` reads a normalised record back from JSON.

Everything here is offline and free: reading directories, parsing text, and
(for the synthetic path) running a deterministic scripted agent on a CPU-only
fixture. No model and no network are involved.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..runtime.state import RunResult
from ..tasks import Task
from .diffs import parse_unified_diff, tree_diff
from .schema import (
    IMPORT_SCHEMA_VERSION,
    ImportedAction,
    ImportedRun,
    ImportSourceError,
    map_tool_name,
)

#: Files/directories never read into an after-state snapshot — caches, vcs,
#: virtualenvs. Mirrors the runtime workspace's ``_COPY_IGNORE`` so a snapshot of a
#: kept workspace matches what the runtime itself copied.
_IGNORE_PARTS: frozenset[str] = frozenset(
    {"__pycache__", ".git", ".pytest_cache", ".venv", ".mypy_cache"}
)
_IGNORE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".pyd")

#: Cap on a single file read into a snapshot, so a stray large/binary artifact
#: cannot bloat an imported record. Larger or undecodable files are skipped.
_MAX_SNAPSHOT_BYTES = 256 * 1024

DEFAULT_AGENT_LABEL = "claude-code-import"


def _ignored(rel: Path) -> bool:
    if any(part in _IGNORE_PARTS for part in rel.parts):
        return True
    return rel.name.endswith(_IGNORE_SUFFIXES)


def read_tree(root: str | Path) -> dict[str, str]:
    """Read a directory into a ``{relative_posix_path: text_content}`` map.

    Skips cache/vcs paths, files over :data:`_MAX_SNAPSHOT_BYTES`, and anything
    that does not decode as UTF-8 (a best-effort text snapshot — binary files are
    out of scope for these tasks and recorded as a limitation). A non-directory
    ``root`` raises :class:`ImportSourceError`.
    """
    base = Path(root)
    if not base.is_dir():
        raise ImportSourceError([f"not a directory: {base}"], source=str(base))
    out: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if _ignored(rel):
            continue
        try:
            if path.stat().st_size > _MAX_SNAPSHOT_BYTES:
                continue
            out[rel.as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unreadable or binary — skip, do not fail the whole import
    return out


def _changed_after_state(
    before: Mapping[str, str], after: Mapping[str, str]
) -> dict[str, str | None]:
    """The after-state of only the paths that changed (``None`` for a deletion)."""
    files: dict[str, str | None] = {}
    for path in sorted(set(before) | set(after)):
        b = before.get(path)
        a = after.get(path)
        if b == a:
            continue
        files[path] = a  # None when the path was deleted
    return files


def import_before_after(
    before: str | Path,
    after: str | Path,
    *,
    task_id: str | None = None,
    agent_label: str = DEFAULT_AGENT_LABEL,
) -> ImportedRun:
    """Import a before/after directory pair into an :class:`ImportedRun`.

    Computes the diff and the changed-file after-state from the two trees, and
    records one ``write_file`` action per changed path so the imported run reads
    as a sequence of edits. This is the only source that always supports
    verification, because it carries the full after-state.
    """
    before_tree = read_tree(before)
    after_tree = read_tree(after)
    diff = tree_diff(before_tree, after_tree)
    files = _changed_after_state(before_tree, after_tree)

    actions: list[ImportedAction] = []
    for i, (path, content) in enumerate(files.items()):
        verb = "delete" if content is None else ("create" if path not in before_tree else "edit")
        actions.append(
            ImportedAction(
                seq=i,
                kind="tool_call",
                tool="apply_patch" if content is None else "write_file",
                raw_tool="Edit",
                summary=f"{verb} {path}",
                args={"path": path},
                data={"ok": True},
            )
        )
    actions.append(
        ImportedAction(
            seq=len(actions),
            kind="finish",
            tool=None,
            raw_tool=None,
            summary=f"applied {len(files)} file change(s)",
        )
    )
    return ImportedRun(
        schema_version=IMPORT_SCHEMA_VERSION,
        source_kind="before_after",
        task_id=task_id,
        agent_label=agent_label,
        actions=tuple(actions),
        diff=diff,
        tests=None,
        files=files,
        source_meta={"before": str(before), "after": str(after)},
    )


def _command_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise one command-log entry into a run_command-shaped data dict."""
    command = entry.get("command", entry.get("argv", []))
    if isinstance(command, str):
        argv = command.split()
    else:
        argv = [str(p) for p in command]
    exit_code = entry.get("exit_code", entry.get("returncode"))
    return {
        "argv": argv,
        "exit_code": exit_code,
        "stdout": str(entry.get("stdout", "")),
        "stderr": str(entry.get("stderr", "")),
        "timed_out": bool(entry.get("timed_out", False)),
        "truncated": False,
    }


def import_diff_and_log(
    diff_text: str,
    commands: Sequence[Mapping[str, Any]] = (),
    *,
    task_id: str | None = None,
    agent_label: str = DEFAULT_AGENT_LABEL,
    test_command: Sequence[str] | None = None,
) -> ImportedRun:
    """Import a unified diff plus a command log into an :class:`ImportedRun`.

    Each command becomes a ``run_shell`` action; a command whose argv matches the
    task's ``test_command`` (or that is flagged ``is_test``) additionally yields the
    declared ``tests`` result (its exit code → ``passed``). No file content is
    available, so the resulting run supports only trust-mode scoring.
    """
    diff = parse_unified_diff(diff_text) if diff_text.strip() else None
    actions: list[ImportedAction] = []
    tests: dict[str, Any] | None = None
    test_argv = list(test_command) if test_command is not None else None

    for i, entry in enumerate(commands):
        rec = _command_record(entry)
        is_test = bool(entry.get("is_test")) or (
            test_argv is not None and rec["argv"] == test_argv
        )
        passed = rec["exit_code"] == 0 and not rec["timed_out"]
        actions.append(
            ImportedAction(
                seq=i,
                kind="tool_call",
                tool="run_tests" if is_test else "run_shell",
                raw_tool="Bash",
                summary=("tests " + ("passed" if passed else "failed"))
                if is_test
                else " ".join(rec["argv"]) or "command",
                args={"command": rec["argv"]},
                data={
                    "ok": passed if is_test else (rec["exit_code"] == 0),
                    "exit_code": rec["exit_code"],
                },
            )
        )
        if is_test and tests is None:
            tests = {**rec, "passed": passed}

    actions.append(
        ImportedAction(
            seq=len(actions),
            kind="finish",
            tool=None,
            raw_tool=None,
            summary="imported from diff + log",
        )
    )
    return ImportedRun(
        schema_version=IMPORT_SCHEMA_VERSION,
        source_kind="diff_and_log",
        task_id=task_id,
        agent_label=agent_label,
        actions=tuple(actions),
        diff=diff,
        tests=tests,
        files={},
        source_meta={"commands": len(commands)},
    )


def import_transcript(
    messages: Sequence[Mapping[str, Any]],
    *,
    task_id: str | None = None,
    agent_label: str = DEFAULT_AGENT_LABEL,
) -> ImportedRun:
    """Import an exported transcript into an :class:`ImportedRun`.

    Each turn may be a tool use (``{"tool": ..., "input": {...}}`` or a Claude-Code
    ``tool_use`` content block) — mapped onto a runtime tool — or plain assistant
    text (kept as a ``message`` action, not a runtime step). A trailing finish is
    synthesised from the last assistant message. The transcript carries the process
    but rarely the change, so scoring is trust-mode unless a diff/tests are
    attached separately.
    """
    actions: list[ImportedAction] = []
    last_text = "imported from transcript"
    seq = 0
    for turn in messages:
        tool_raw, args, summary = _transcript_tool(turn)
        if tool_raw is not None:
            actions.append(
                ImportedAction(
                    seq=seq,
                    kind="tool_call",
                    tool=map_tool_name(tool_raw),
                    raw_tool=tool_raw,
                    summary=summary or tool_raw,
                    args=args,
                    data={"ok": True},
                )
            )
            seq += 1
            continue
        text = _transcript_text(turn)
        if text:
            last_text = text
            actions.append(
                ImportedAction(
                    seq=seq,
                    kind="message",
                    tool=None,
                    raw_tool=None,
                    summary=text[:200],
                    args={},
                    data={},
                )
            )
            seq += 1

    actions.append(
        ImportedAction(seq=seq, kind="finish", tool=None, raw_tool=None, summary=last_text[:200])
    )
    return ImportedRun(
        schema_version=IMPORT_SCHEMA_VERSION,
        source_kind="transcript",
        task_id=task_id,
        agent_label=agent_label,
        actions=tuple(actions),
        diff=None,
        tests=None,
        files={},
        source_meta={"turns": len(messages)},
    )


def _transcript_tool(turn: Mapping[str, Any]) -> tuple[str | None, dict[str, Any], str]:
    """Extract a (raw_tool_name, args, summary) from a transcript turn, if any."""
    # Flat shape: {"tool": "Edit", "input": {...}} or {"tool_name": ...}.
    name = turn.get("tool") or turn.get("tool_name")
    if isinstance(name, str):
        args = turn.get("input") or turn.get("args") or {}
        return name, dict(args) if isinstance(args, Mapping) else {}, str(turn.get("summary", ""))
    # Claude-Code content-block shape: content is a list of blocks, one a tool_use.
    content = turn.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                args = block.get("input") or {}
                return (
                    str(block.get("name", "tool")),
                    dict(args) if isinstance(args, Mapping) else {},
                    str(block.get("name", "")),
                )
    return None, {}, ""


def _transcript_text(turn: Mapping[str, Any]) -> str:
    """Best-effort plain-text content of a transcript turn."""
    content = turn.get("content") or turn.get("text")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(b.get("text", ""))
            for b in content
            if isinstance(b, Mapping) and b.get("type") == "text"
        ]
        return " ".join(p for p in parts if p)
    return ""


def export_run(
    result: RunResult,
    *,
    files: Mapping[str, str | None] | None = None,
    source_kind: str = "exported",
    agent_label: str | None = None,
) -> ImportedRun:
    """Turn a :class:`RunResult` into an :class:`ImportedRun`.

    This is how a real run becomes an importable record: each step maps to an
    imported action, and the run's diff/tests carry over. ``files`` is the optional
    after-state snapshot (so the exported run can later be *verified*); without it
    the export is process-and-outcome only. Underlies :func:`synthesize_import`.
    """
    actions: list[ImportedAction] = []
    for step in result.steps:
        if step.action_kind == "finish":
            actions.append(
                ImportedAction(
                    seq=step.index,
                    kind="finish",
                    tool=None,
                    raw_tool=None,
                    summary=step.message or "done",
                )
            )
            continue
        res = step.result
        data: dict[str, Any] = {
            "ok": bool(res.ok) if res is not None else None,
            "allowed": step.allowed,
        }
        if res is not None and "exit_code" in res.data:
            data["exit_code"] = res.data.get("exit_code")
        actions.append(
            ImportedAction(
                seq=step.index,
                kind="tool_call",
                tool=step.tool,
                raw_tool=step.tool,
                summary=res.summary if res is not None else (step.tool or ""),
                args=dict(step.args),
                data=data,
            )
        )
    return ImportedRun(
        schema_version=IMPORT_SCHEMA_VERSION,
        source_kind=source_kind,
        task_id=result.task_id,
        agent_label=agent_label or f"exported:{result.agent}",
        actions=tuple(actions),
        diff=dict(result.diff) if result.diff is not None else None,
        tests=dict(result.tests) if result.tests is not None else None,
        files=dict(files) if files else {},
        source_meta={"exported_from_agent": result.agent, "outcome": result.outcome},
    )


def synthesize_import(
    task: Task,
    *,
    agent: str = "scripted",
    config: Any = None,
    registry: Any = None,
    agent_label: str = "claude-code-synthetic",
) -> ImportedRun:
    """Generate a deterministic, offline synthetic Claude-Code-like import for ``task``.

    Runs a built-in deterministic agent (default: the scripted solution) over the
    task with the workspace kept, snapshots the changed files as the after-state,
    then exports the run. The result is a self-contained :class:`ImportedRun` that
    round-trips: importing and scoring it reproduces the native run's verdict, in
    both trust and verify mode. Requires a task with a built-in solution (raises
    :class:`KeyError` otherwise).
    """
    from ..agents import build_scripted_agent  # local: keep importers a leaf consumer
    from ..runtime import RunConfig, run_task

    built = build_scripted_agent(task) if agent == "scripted" else None
    if built is None:  # pragma: no cover - only 'scripted' is supported today
        raise ValueError(f"unknown synthesize agent {agent!r} (only 'scripted' is supported)")

    run_config = config or RunConfig()
    # Keep the workspace so we can snapshot the after-state, regardless of caller config.
    from dataclasses import replace

    run_config = replace(run_config, keep_workspace=True)
    result = run_task(task, built, config=run_config, registry=registry)

    files: dict[str, str | None] = {}
    if result.workspace and result.diff is not None:
        files = _snapshot_changed(Path(result.workspace), result.diff)
    # Best-effort cleanup of the kept workspace now that we have the snapshot.
    if result.workspace:
        import shutil

        shutil.rmtree(result.workspace, ignore_errors=True)

    return export_run(result, files=files, source_kind="synthetic", agent_label=agent_label)


def _snapshot_changed(workspace: Path, diff: Mapping[str, Any]) -> dict[str, str | None]:
    """Read the after-state content of every path the run's diff touched."""
    paths: list[str] = [f["path"] for f in diff.get("files", []) if "path" in f]
    paths += list(diff.get("untracked", []))
    files: dict[str, str | None] = {}
    for rel in sorted(set(paths)):
        path = workspace / rel
        if not path.is_file():
            files[rel] = None  # deleted by the run
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - defensive
            continue
    return files


def load_import_source(path: str | Path) -> ImportedRun:
    """Load a normalised :class:`ImportedRun` from a JSON file (validated)."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ImportSourceError([f"could not read {p}: {exc}"], source=str(p)) from exc
    except json.JSONDecodeError as exc:
        raise ImportSourceError([f"not valid JSON: {exc}"], source=str(p)) from exc
    return ImportedRun.from_dict(data, source=str(p))


def write_import_source(imported: ImportedRun, path: str | Path) -> Path:
    """Write an :class:`ImportedRun` to ``path`` as indented JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(imported.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out
