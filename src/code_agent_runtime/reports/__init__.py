"""Result reports (Milestone 8).

Render a :class:`~code_agent_runtime.scoring.SuiteResult` for humans: a Markdown
report (:func:`suite_to_markdown`) for terminals and docs, and a standalone HTML
report (:func:`suite_to_html`) for the browser. Both share the result table the
plan specifies — task id, agent, pass/fail, runtime, tool calls, commands,
failure reason — and the same honest notes on what a verdict means.

Reports consume the suite result as data; they import the scoring layer but never
the runtime.
"""

from __future__ import annotations

from .html import suite_to_html
from .markdown import suite_to_markdown, verdict_label

__all__ = ["suite_to_markdown", "suite_to_html", "verdict_label"]
