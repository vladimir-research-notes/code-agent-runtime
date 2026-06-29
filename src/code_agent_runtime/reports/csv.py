"""CSV report for a suite result (Milestone 12).

Renders a :class:`~code_agent_runtime.scoring.SuiteResult` as comma-separated
rows — one per run — for spreadsheets, ``pandas``, or a quick ``grep``/``cut``.
The columns mirror the Markdown/HTML result table (task id, agent, scoring method,
verdict, effort signals, failure reason) so the three formats describe the same
data.

``runtime_seconds`` is wall-clock and machine-dependent. It is included by
default (it is real evidence of a run), but ``include_runtime=False`` drops it so
the output is fully deterministic — used for the canonical, committed case-study
CSV that should not churn from machine to machine.
"""

from __future__ import annotations

import csv
import io

from ..scoring import SuiteResult
from .markdown import verdict_label

#: Deterministic columns (everything except the wall-clock ``runtime_seconds``).
_BASE_COLUMNS = (
    "task_id",
    "agent",
    "scoring_method",
    "verdict",
    "outcome",
    "passed",
    "tool_calls",
    "commands",
    "blocked",
    "phase_reached",
    "stop_reason",
    "failure_reason",
)


def suite_to_csv(suite: SuiteResult, *, include_runtime: bool = True) -> str:
    """Render ``suite`` as a CSV string (with a header row).

    With ``include_runtime`` (the default) a ``runtime_seconds`` column is
    inserted after ``verdict``; set it ``False`` for a deterministic, machine
    independent table.
    """
    columns = list(_BASE_COLUMNS)
    if include_runtime:
        columns.insert(columns.index("verdict") + 1, "runtime_seconds")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for rec in suite.records:
        row = {
            "task_id": rec.task_id,
            "agent": rec.agent,
            "scoring_method": rec.score.get("method", ""),
            "verdict": verdict_label(rec),
            "outcome": rec.outcome,
            "passed": "" if rec.passed is None else str(rec.passed).lower(),
            "tool_calls": rec.tool_call_count,
            "commands": rec.command_count,
            "blocked": rec.blocked_count,
            "phase_reached": rec.phase_reached,
            "stop_reason": rec.stop_reason,
            "failure_reason": rec.failure_reason or "",
            "runtime_seconds": f"{rec.runtime_seconds:.4f}",
        }
        writer.writerow([row[c] for c in columns])
    return buf.getvalue()
