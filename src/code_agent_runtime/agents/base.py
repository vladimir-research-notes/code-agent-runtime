"""Agent abstractions for the runtime loop (Milestone 4).

An *agent* is whatever decides what to do next. The runtime treats every agent —
the deterministic baselines here, and the optional LLM adapters of later
milestones — through one narrow interface so the loop, the (future) trace
recorder, and the scorer never need to know which kind of agent produced a run.

The contract is intentionally tiny:

- the runtime hands the agent an :class:`Observation` (the task, the step index,
  and the result of the agent's previous action);
- the agent returns one :class:`AgentAction`: either *run a tool* (a
  :class:`~code_agent_runtime.tools.ToolCall`) or *finish*.

That is the whole protocol. Agents do not touch the filesystem, dispatch tools,
or run commands themselves — the runtime owns side effects and gating so that a
run is reproducible and every action is recordable. Keeping the deterministic
mock/scripted agents first-class (no model, no network, no cost) is a project
constraint, not an afterthought; see ``docs/PLAN.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from ..tasks import Task
from ..tools import ToolCall, ToolResult


@dataclass(frozen=True)
class Observation:
    """What the runtime shows an agent before it picks its next action.

    ``last_result`` is the structured result of the agent's previous tool call,
    or ``None`` on the first step. Deterministic agents (mock, scripted) ignore
    it; it exists so reactive agents have something to react to without the
    runtime having to special-case them.
    """

    task: Task
    step: int
    last_result: ToolResult | None = None


@dataclass(frozen=True)
class AgentAction:
    """One decision: run a tool, or finish the run.

    Construct via :meth:`tool` or :meth:`finish` rather than by hand so the
    ``kind``/``call`` invariants always hold. ``message`` is an optional,
    human-readable note (a rationale or a finish reason) carried into the trace.
    """

    kind: str
    call: ToolCall | None = None
    message: str | None = None

    #: The two action kinds. A closed vocabulary, like the tool categories.
    TOOL: ClassVar[str] = "tool"
    FINISH: ClassVar[str] = "finish"

    @classmethod
    def tool(
        cls,
        name_or_call: str | ToolCall,
        args: Mapping[str, Any] | None = None,
        *,
        message: str | None = None,
    ) -> AgentAction:
        """Build a tool action from a :class:`ToolCall` or a name + args."""
        if isinstance(name_or_call, ToolCall):
            call = name_or_call
        else:
            call = ToolCall(name_or_call, dict(args or {}))
        return cls(kind=cls.TOOL, call=call, message=message)

    @classmethod
    def finish(cls, message: str | None = None) -> AgentAction:
        """Build a finish action with an optional reason."""
        return cls(kind=cls.FINISH, message=message)

    @property
    def is_finish(self) -> bool:
        return self.kind == self.FINISH

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "call": self.call.to_dict() if self.call is not None else None,
            "message": self.message,
        }


class Agent:
    """Base class for an agent the runtime can drive.

    Subclasses set :attr:`name` and implement :meth:`propose`. :meth:`reset` is
    called once before each run so a stateful agent (e.g. the scripted replayer)
    can rewind; the default is a no-op.
    """

    #: Short, stable agent name recorded in results (e.g. ``"mock"``).
    name: ClassVar[str] = ""

    def reset(self, task: Task) -> None:  # noqa: D401 - simple hook
        """Prepare to drive ``task`` from the start. Override if stateful."""

    def propose(self, observation: Observation) -> AgentAction:
        """Return the next action given ``observation``."""
        raise NotImplementedError
