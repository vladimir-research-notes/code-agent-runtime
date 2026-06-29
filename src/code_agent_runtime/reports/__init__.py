"""Result reports (Milestones 8–9).

Render the scoring layer's data structures for humans:

- a suite result as a Markdown report (:func:`suite_to_markdown`) for terminals
  and docs, a standalone HTML report (:func:`suite_to_html`) for the browser, and
  a CSV table (:func:`suite_to_csv`) for spreadsheets — all sharing the plan's
  result table (task id, agent, pass/fail, runtime, tool calls, commands, failure
  reason) and the same honest notes on what a verdict means;
- a regression comparison (:func:`regression_to_markdown`) and a flakiness report
  (:func:`flakiness_to_markdown`) as Markdown (Milestone 9).

Reports consume the scoring data structures; they import the scoring layer but
never the runtime.
"""

from __future__ import annotations

from .csv import suite_to_csv
from .html import suite_to_html
from .markdown import suite_to_markdown, verdict_label
from .regression import flakiness_to_markdown, regression_to_markdown

__all__ = [
    "suite_to_markdown",
    "suite_to_html",
    "suite_to_csv",
    "verdict_label",
    "regression_to_markdown",
    "flakiness_to_markdown",
]
