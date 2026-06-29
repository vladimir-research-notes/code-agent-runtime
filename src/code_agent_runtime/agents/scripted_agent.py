"""``scripted`` — a deterministic replay agent (Milestone 4).

A scripted agent is handed a fixed sequence of actions when it is built and
replays them one per step, then finishes. It ignores observations entirely, so a
run is fully determined by its script: the same script over the same fixture
produces the same trace every time. This makes scripted agents the reproducible
"known-good solution" baseline — useful for proving the runtime can carry a task
from a failing fixture to passing tests without any model in the loop.

The script may mix :class:`AgentAction`, :class:`~code_agent_runtime.tools.ToolCall`,
and ``(tool_name, args)`` tuples; all are coerced to actions. Building scripts
that actually solve the shipped example tasks lives in :mod:`.solutions`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..tasks import Task
from ..tools import ToolCall
from .base import Agent, AgentAction, Observation

#: One accepted script element: a ready action, a tool call, or (name, args).
ScriptStep = AgentAction | ToolCall | tuple[str, Mapping[str, Any]]


class ScriptedAgent(Agent):
    """Replay a predetermined list of actions, then finish."""

    name = "scripted"

    def __init__(self, script: Iterable[ScriptStep], *, name: str | None = None) -> None:
        self._actions = [self._coerce(step) for step in script]
        self._cursor = 0
        if name is not None:
            self.name = name

    @staticmethod
    def _coerce(step: ScriptStep) -> AgentAction:
        if isinstance(step, AgentAction):
            return step
        if isinstance(step, ToolCall):
            return AgentAction.tool(step)
        if isinstance(step, tuple) and len(step) == 2 and isinstance(step[0], str):
            name, args = step
            return AgentAction.tool(name, args)
        raise TypeError(
            "scripted step must be an AgentAction, a ToolCall, or a (name, args) "
            f"tuple; got {type(step).__name__}"
        )

    def reset(self, task: Task) -> None:
        self._cursor = 0

    def propose(self, observation: Observation) -> AgentAction:
        if self._cursor >= len(self._actions):
            return AgentAction.finish("scripted plan complete")
        action = self._actions[self._cursor]
        self._cursor += 1
        return action
