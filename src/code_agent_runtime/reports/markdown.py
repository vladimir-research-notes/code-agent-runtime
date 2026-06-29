"""Markdown report for a suite result (Milestone 8).

Renders a :class:`~code_agent_runtime.scoring.SuiteResult` as a Markdown document:
a summary line, the per-run result table the plan specifies (task id, agent,
pass/fail, runtime, tool calls, commands, failure reason), and an honest note on
what the verdicts do and do not mean. The same table is emitted as HTML by
:mod:`.html`.
"""

from __future__ import annotations

from ..scoring import Outcome, SuiteResult
from ..scoring.suite import EvalRecord

_COLUMNS = (
    "task id",
    "agent",
    "method",
    "result",
    "runtime (s)",
    "tool calls",
    "commands",
    "failure reason",
)


def verdict_label(rec: EvalRecord) -> str:
    """The pass/fail cell for a record: ``pass``/``fail`` or the outcome name."""
    if rec.passed is True:
        return "pass"
    if rec.passed is False:
        return "fail"
    return rec.outcome  # not_scored / error


def _cell(text: object) -> str:
    """Sanitise a value for a Markdown table cell (escape pipes, one line)."""
    s = "" if text is None else str(text)
    return " ".join(s.split()).replace("|", "\\|")


def _row(values: tuple[object, ...]) -> str:
    return "| " + " | ".join(_cell(v) for v in values) + " |"


def suite_to_markdown(suite: SuiteResult, *, title: str = "Evaluation results") -> str:
    """Render ``suite`` as a Markdown report string."""
    totals = suite.totals()
    lines: list[str] = [f"# {title}"]
    if suite.label:
        lines.append(f"\n_Suite: {suite.label}_")
    lines.append(
        f"\n**{suite.total} run(s)** — "
        f"{totals[Outcome.PASSED]} passed, {totals[Outcome.FAILED]} failed, "
        f"{totals[Outcome.NOT_SCORED]} not scored, {totals[Outcome.ERROR]} errored."
    )

    lines.append("")
    lines.append(_row(_COLUMNS))
    lines.append("| " + " | ".join("---" for _ in _COLUMNS) + " |")
    for rec in suite.records:
        lines.append(
            _row(
                (
                    rec.task_id,
                    rec.agent,
                    rec.score.get("method", ""),
                    verdict_label(rec),
                    f"{rec.runtime_seconds:.3f}",
                    rec.tool_call_count,
                    rec.command_count,
                    rec.failure_reason or "",
                )
            )
        )

    if suite.skipped:
        lines.append("")
        lines.append("## Skipped (agent not applicable to task)")
        for s in suite.skipped:
            lines.append(f"- `{s.get('agent')}` on `{s.get('task_id')}`")

    lines.append("")
    lines.append("## Notes")
    lines.append(
        "- `result` is the scored verdict: `pass`/`fail`, or `not_scored` for tasks "
        "scored by inspection (`scoring_method: none`)."
    )
    lines.append(
        "- A passing test command is evidence, not proof, that a change is correct; "
        "`diff_constraint` checks scope, not correctness."
    )
    lines.append(
        "- Runtime is wall-clock and machine-dependent; tool/command counts are "
        "deterministic and reproducible."
    )
    return "\n".join(lines) + "\n"
