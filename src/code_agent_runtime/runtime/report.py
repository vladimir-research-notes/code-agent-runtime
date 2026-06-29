"""A concise text report for a single run (Milestone 4).

This is the runtime's own human-readable summary of a :class:`RunResult` for the
``run`` CLI command. It is deliberately small. The dedicated reporting layer —
Markdown and HTML reports over a *suite* of runs, with regression comparison —
is Milestone 8 (``reports/``); this exists so a single run is legible at the
terminal today, and JSON (``RunResult.to_dict``) covers machine consumption.
"""

from __future__ import annotations

from .state import RunResult


def format_run_report(result: RunResult) -> str:
    """Render a one-run summary: outcome, counts, tests, diff, and each step."""
    lines = [
        f"Run report: {result.task_id}",
        f"  agent        : {result.agent}",
        f"  outcome      : {result.outcome}",
        f"  phase reached: {result.phase_reached}",
        f"  steps        : {len(result.steps)} "
        f"({result.tool_call_count} tool call(s), {result.command_count} command(s))",
        f"  stop reason  : {result.stop_reason}",
    ]
    if result.tests is not None:
        verdict = "passed" if result.tests.get("passed") else "failed"
        lines.append(f"  tests        : {verdict} (exit {result.tests.get('exit_code')})")
    if result.diff is not None:
        files = result.diff.get("files", [])
        untracked = result.diff.get("untracked", [])
        lines.append(
            f"  diff         : {len(files)} tracked file(s) changed, "
            f"+{result.diff.get('insertions', 0)}/-{result.diff.get('deletions', 0)}"
            + (f", {len(untracked)} new file(s)" if untracked else "")
        )
    elif not result.git:
        lines.append("  diff         : (not captured — workspace is not a git repo)")
    lines.append(f"  score        : {result.score.get('detail')}")
    if result.error:
        lines.append(f"  error        : {result.error}")
    workspace_state = "kept" if result.kept_workspace else "removed"
    lines.append(f"  workspace    : {result.workspace} ({workspace_state})")

    if result.steps:
        lines.append("  steps:")
        for step in result.steps:
            if step.action_kind == "finish":
                lines.append(f"    {step.index}. finish — {step.message or 'done'}")
                continue
            mark = "ok" if (step.result and step.result.ok) else "FAIL"
            gate = "" if step.allowed else " [BLOCKED]"
            summary = step.result.summary if step.result else ""
            lines.append(f"    {step.index}. {step.tool}{gate} [{mark}] {summary}")
    return "\n".join(lines)
