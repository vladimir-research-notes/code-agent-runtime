"""Render a reconstructed run as text or Markdown (Milestone 6).

:mod:`.replay` turns a stored :class:`~code_agent_runtime.traces.schema.Trace`
back into a :class:`~code_agent_runtime.traces.replay.ReplayedRun`; this module
renders that view for a human. Two renderers:

- :func:`summarize_trace` — a compact, one-screen text summary for the terminal:
  header, counts, the verdict (or failure point), the action timeline, and any
  anomalies. This is the "a sample trace can be summarized" deliverable.
- :func:`trace_to_markdown` — a fuller Markdown report (the "a Markdown report can
  be generated" deliverable): the same reconstruction as headings and tables,
  plus the test output tail and the unified diff, suitable for a PR comment or an
  archived run record.

Both accept a :class:`Trace` and reconstruct internally, so a caller that only
has a loaded trace need not touch :mod:`.replay`. Rendering is pure string-
building; nothing here reads the clock or the filesystem.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .replay import ReplayedRun, replay_trace
from .schema import Trace

#: How many trailing lines of captured test output the Markdown report shows.
_TEST_TAIL_LINES = 20
#: How many lines of the unified diff the Markdown report shows before noting a cut.
_DIFF_MAX_LINES = 200


def summarize_trace(trace: Trace) -> str:
    """Render a compact text summary of ``trace`` (reconstructed via replay)."""
    run = replay_trace(trace)
    lines = [
        f"Trace: {run.trace_id}",
        f"  task     : {run.task_id} — {run.task_title}",
        f"  agent    : {run.agent}",
        f"  outcome  : {run.outcome}",
        f"  started  : {run.started_at_iso}",
        f"  duration : {_fmt_duration(run.duration_seconds)}",
        f"  steps    : {_counts_line(run)}",
    ]
    if run.tests is not None:
        lines.append(f"  tests    : {_tests_line(run.tests)}")
    if run.diff is not None:
        lines.append(f"  diff     : {_diff_line(run.diff)}")
    lines.append(f"  verdict  : {_verdict_line(run)}")

    lines.append("  timeline :")
    for ev in run.timeline:
        lines.append(f"    [{ev.elapsed_seconds:6.2f}s] {ev.kind:<18} {ev.summary}")

    if run.anomalies:
        lines.append(f"  anomalies ({len(run.anomalies)}):")
        for a in run.anomalies:
            marker = " <- failure point" if a is run.failure_point else ""
            lines.append(f"    - [{a.kind}] seq {a.seq} ({a.phase}): {a.detail}{marker}")
    return "\n".join(lines)


def trace_to_markdown(trace: Trace) -> str:
    """Render a Markdown report of ``trace`` (reconstructed via replay)."""
    run = replay_trace(trace)
    out: list[str] = []

    out.append(f"# Trace report: {run.trace_id}")
    out.append("")
    out.append(f"- **Task:** `{run.task_id}` — {run.task_title}")
    out.append(f"- **Agent:** {run.agent}")
    out.append(f"- **Outcome:** {run.outcome}")
    out.append(f"- **Started:** {run.started_at_iso}")
    out.append(f"- **Duration:** {_fmt_duration(run.duration_seconds)}")
    out.append(f"- **Steps:** {_counts_line(run)}")
    out.append("")

    out.append("## Verdict")
    out.append("")
    if run.failure_point is None:
        out.append(f"Run **{run.outcome}** with no failure point detected.")
        if run.anomalies:
            out.append("")
            out.append(
                f"({len(run.anomalies)} anomaly(ies) recorded but the run still "
                f"reached its verdict — see Anomalies below.)"
            )
    else:
        fp = run.failure_point
        out.append(
            f"**Failure point:** `{fp.kind}` at sequence {fp.seq} "
            f"(phase `{fp.phase}`, {fp.elapsed_seconds:.2f}s) — {fp.detail}"
        )
    out.append("")

    out.append("## Timeline")
    out.append("")
    out.append("| seq | elapsed | phase | event | summary |")
    out.append("| ---: | ---: | --- | --- | --- |")
    for ev in run.timeline:
        out.append(
            f"| {ev.seq} | {ev.elapsed_seconds:.2f}s | {ev.phase} | "
            f"{ev.kind} | {_md_cell(ev.summary)} |"
        )
    out.append("")

    if run.tool_calls:
        out.append("## Tool calls")
        out.append("")
        out.append("| step | tool | allowed | ok | exit | summary |")
        out.append("| ---: | --- | :---: | :---: | ---: | --- |")
        for tc in run.tool_calls:
            out.append(
                f"| {_blank_if_none(tc.step_index)} | `{tc.tool}` | "
                f"{_yn(tc.allowed)} | {_ok_cell(tc.ok)} | "
                f"{_blank_if_none(tc.exit_code)} | {_md_cell(tc.summary)} |"
            )
        out.append("")

    if run.tests is not None:
        out.append("## Tests")
        out.append("")
        out.append(f"- Result: **{_tests_line(run.tests)}**")
        tail = _output_tail(run.tests)
        if tail:
            out.append("")
            out.append("```")
            out.extend(tail)
            out.append("```")
        out.append("")

    if run.diff is not None:
        out.append("## Diff")
        out.append("")
        out.append(f"- {_diff_line(run.diff)}")
        out.extend(_diff_file_list(run.diff))
        diff_block = _diff_block(run.diff)
        if diff_block:
            out.append("")
            out.append("```diff")
            out.extend(diff_block)
            out.append("```")
        out.append("")

    if run.anomalies:
        out.append("## Anomalies")
        out.append("")
        out.append(
            "What a bare pass/fail verdict can hide: blocked or failed tool "
            "calls, a failing test command, or a run that errored out."
        )
        out.append("")
        for a in run.anomalies:
            marker = " — **failure point**" if a is run.failure_point else ""
            out.append(
                f"- `{a.kind}` (seq {a.seq}, phase `{a.phase}`): {a.detail}{marker}"
            )
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# -- shared field renderers -------------------------------------------------


def _counts_line(run: ReplayedRun) -> str:
    return (
        f"{run.tool_call_count} tool call(s) "
        f"({run.blocked_count} blocked, {run.failed_tool_count} failed), "
        f"{run.command_count} command(s)"
    )


def _verdict_line(run: ReplayedRun) -> str:
    if run.failure_point is None:
        if run.anomalies:
            return f"{run.outcome} (with {len(run.anomalies)} recorded anomaly(ies))"
        return f"{run.outcome}"
    fp = run.failure_point
    return f"{run.outcome} — failure point [{fp.kind}] at seq {fp.seq}: {fp.detail}"


def _tests_line(tests: Mapping[str, Any]) -> str:
    if tests.get("timed_out"):
        return "timed out"
    passed = tests.get("passed")
    verdict = "passed" if passed else "failed"
    return f"{verdict} (exit {tests.get('exit_code')})"


def _diff_line(diff: Mapping[str, Any]) -> str:
    files = diff.get("files", [])
    untracked = diff.get("untracked", [])
    trunc = " [truncated]" if diff.get("truncated") else ""
    extra = f", {len(untracked)} new file(s)" if untracked else ""
    return (
        f"{len(files)} tracked file(s) changed, "
        f"+{diff.get('insertions', 0)}/-{diff.get('deletions', 0)}{extra}{trunc}"
    )


# -- Markdown helpers -------------------------------------------------------


def _diff_file_list(diff: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for f in diff.get("files", []):
        if f.get("binary"):
            lines.append(f"  - `{f.get('path')}` (binary)")
        else:
            lines.append(
                f"  - `{f.get('path')}` (+{f.get('insertions', 0)}/-{f.get('deletions', 0)})"
            )
    for path in diff.get("untracked", []):
        lines.append(f"  - `{path}` (new, untracked)")
    return lines


def _diff_block(diff: Mapping[str, Any]) -> list[str]:
    text = diff.get("diff") or ""
    if not text.strip():
        return []
    lines = text.splitlines()
    if len(lines) > _DIFF_MAX_LINES:
        shown = lines[:_DIFF_MAX_LINES]
        shown.append(f"... ({len(lines) - _DIFF_MAX_LINES} more line(s) omitted)")
        return shown
    return lines


def _output_tail(tests: Mapping[str, Any]) -> list[str]:
    """The last few lines of captured test output (stdout, else stderr)."""
    text = tests.get("stdout") or tests.get("stderr") or ""
    if not text.strip():
        return []
    lines = text.splitlines()
    if len(lines) > _TEST_TAIL_LINES:
        return [f"... ({len(lines) - _TEST_TAIL_LINES} earlier line(s) omitted)"] + lines[
            -_TEST_TAIL_LINES:
        ]
    return lines


def _md_cell(text: str) -> str:
    """Escape a value for a Markdown table cell (pipes break the column)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _yn(value: bool) -> str:
    return "yes" if value else "**no**"


def _ok_cell(ok: bool | None) -> str:
    if ok is None:
        return "—"
    return "ok" if ok else "**fail**"


def _blank_if_none(value: Any) -> str:
    return "" if value is None else str(value)


# -- formatting -------------------------------------------------------------


def _fmt_duration(seconds: float | None) -> str:
    return "—" if seconds is None else f"{seconds:.2f}s"
