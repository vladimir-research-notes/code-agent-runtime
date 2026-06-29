"""The agent↔model wire protocol: prompts in, one action out (Milestone 10).

The runtime's :class:`~code_agent_runtime.agents.base.AgentAction` is the only
thing the loop understands, so a model-backed agent needs a contract for turning
free-form model text into exactly one action per turn. That contract lives here,
isolated from any client or network code so it can be unit-tested directly:

- :func:`build_system_prompt` / :func:`render_task_message` /
  :func:`render_step_message` build what we send the model — the role, the tool
  catalogue, the required reply format, the task, and the result of the previous
  tool call.
- :func:`parse_action` turns the model's reply back into an
  :class:`AgentAction`, raising :class:`ActionParseError` when the reply does not
  contain a usable action.

The reply format is intentionally minimal and robust: the model must emit a
single JSON object naming either a tool call or a finish. We extract the first
balanced ``{...}`` (tolerating surrounding prose or a ```` ```json ```` fence),
so a chatty model still parses. :func:`action_json` / :func:`finish_json` emit
that same format and are used to script the offline fake client from a known-good
solution, which is how the whole path is demonstrated without a paid call.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from ...tasks import Task
from ...tools import ToolCall
from ...tools.base import ToolSpec
from ..base import AgentAction


class ActionParseError(ValueError):
    """The model's reply did not contain a parseable tool/finish action."""


_RESPONSE_RULES = (
    "Reply with EXACTLY ONE JSON object and nothing else. To call a tool:\n"
    '  {"tool": "<tool_name>", "args": {<arguments>}}\n'
    "To finish the task (you are done, or cannot proceed):\n"
    '  {"action": "finish", "message": "<why you are stopping>"}\n'
    "Do not wrap multiple actions in one reply. Do not invent tools or arguments."
)


def _render_tool_catalogue(specs: Sequence[ToolSpec]) -> str:
    """Render the available tools and their parameters for the system prompt."""
    if not specs:
        return "  (no tools available)"
    lines: list[str] = []
    for spec in specs:
        params = ", ".join(
            f"{p.name}:{p.type}{'' if p.required else '?'}" for p in spec.params
        ) or "no parameters"
        lines.append(f"  - {spec.name} [{spec.category}] ({params}) — {spec.summary}")
    return "\n".join(lines)


def build_system_prompt(task: Task, specs: Sequence[ToolSpec]) -> str:
    """Build the system prompt: the agent's role, its tools, and the reply format."""
    return (
        "You are a coding agent operating inside a sandboxed workspace. You act "
        "only by calling the tools listed below; you cannot run anything else. "
        "All paths are relative to the workspace root and must stay inside it.\n\n"
        "Available tools:\n"
        f"{_render_tool_catalogue(specs)}\n\n"
        f"{_RESPONSE_RULES}\n\n"
        "Work in small steps: inspect before editing, make the smallest change "
        "that satisfies the task, then finish."
    )


def render_task_message(task: Task, specs: Sequence[ToolSpec]) -> str:
    """The first user turn: the task to solve and a reminder of the reply format."""
    allowed = ", ".join(s.name for s in specs) or "(none)"
    test_cmd = task.test_command_str or "(none)"
    return (
        f"Task: {task.title}\n"
        f"Task id: {task.id}\n"
        f"Allowed tools: {allowed}\n"
        f"Test command (run for you after you finish): {test_cmd}\n\n"
        f"Instructions:\n{task.prompt}\n\n"
        "Respond with one JSON action."
    )


def render_step_message(observation) -> str:
    """A follow-up user turn: the result of the previous tool call.

    Reactive models use this to decide the next action; the offline fake ignores
    it. ``observation.last_result`` is a
    :class:`~code_agent_runtime.tools.ToolResult` (or ``None`` defensively).
    """
    result = getattr(observation, "last_result", None)
    if result is None:  # pragma: no cover - first step uses render_task_message
        return "No previous result. Respond with one JSON action."
    status = "ok" if result.ok else "error"
    body = f"Previous tool '{result.tool}' returned [{status}]: {result.summary}"
    if not result.ok and result.error:
        body += f"\nerror: {result.error}"
    return f"{body}\n\nRespond with one JSON action (call a tool or finish)."


def _extract_json_object(text: str) -> str:
    """Return the first balanced ``{...}`` substring of ``text``.

    Tolerant of surrounding prose and code fences; tracks brace depth while
    ignoring braces inside JSON strings (so a brace in a patch body is fine).
    Raises :class:`ActionParseError` if no balanced object is present.
    """
    start = text.find("{")
    if start == -1:
        raise ActionParseError("model reply contained no JSON object")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ActionParseError("model reply had an unbalanced JSON object")


def parse_action(text: str) -> AgentAction:
    """Parse a model reply into a single :class:`AgentAction`.

    Accepts ``{"tool": ..., "args": {...}}`` (a tool call) or
    ``{"action": "finish", ...}`` / ``{"finish": true}`` / ``{"done": true}`` (a
    finish). Raises :class:`ActionParseError` on anything else, so the agent can
    end the run cleanly instead of the loop crashing on a malformed reply.
    """
    blob = _extract_json_object(text)
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ActionParseError(f"model reply was not valid JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise ActionParseError("model action must be a JSON object")

    action = obj.get("action")
    if action == "finish" or obj.get("finish") is True or obj.get("done") is True:
        msg = obj.get("message")
        return AgentAction.finish(str(msg) if msg is not None else "model finished")

    tool = obj.get("tool") or (obj.get("name") if action == "tool" else None)
    if isinstance(tool, str) and tool:
        args = obj.get("args", {})
        if not isinstance(args, dict):
            raise ActionParseError(f"'args' for tool {tool!r} must be an object")
        return AgentAction.tool(tool, args)

    raise ActionParseError(
        "model action named neither a tool ('tool') nor a finish ('action':'finish')"
    )


def action_json(call: ToolCall) -> str:
    """Render a tool call as the wire-format JSON the protocol parses."""
    return json.dumps({"tool": call.tool, "args": dict(call.args)})


def finish_json(message: str) -> str:
    """Render a finish action as the wire-format JSON the protocol parses."""
    return json.dumps({"action": "finish", "message": message})
