"""``llm`` — a cost-guarded, model-backed agent (Milestone 10).

The :class:`LLMAgent` plugs a model into the same one-action-per-step contract the
deterministic baselines use, so the runtime, tracer, and scorer treat it exactly
like any other agent. Every call funnels through the safety machinery this
milestone adds, in this order on each step:

1. render the next user turn (the task, or the previous tool result) and append
   it to the transcript — **after** transcript redaction, so a secret a tool
   surfaced never travels to the model or onto disk;
2. look the request up in the :class:`~.cache.ResponseCache` — a hit is free and
   skips everything below;
3. on a miss, ask the :class:`~.budget.BudgetGuard` to clear the call's worst
   case *before* contacting the client (a hard pre-call stop), make the call,
   then record the actual usage and cache the response;
4. parse the reply into one :class:`AgentAction`; a malformed reply ends the run
   cleanly rather than crashing the loop.

The agent never imports a network library. It is handed an
:class:`~.client.LLMClient`; the offline :class:`~.client.FakeLLMClient` makes the
whole path runnable — and the budget guard, cache, and redaction observable — with
no API key. :func:`build_fake_llm_agent` wires that offline path from a task's
known-good solution; :func:`build_llm_agent` is the general constructor; and
:func:`dry_run_plan` reports what a real first call *would* send and cost without
making it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ...sandbox.secret_scanner import redact_text
from ...tasks import Task
from ...tools import build_registry
from ...tools.base import ToolSpec
from ..base import Agent, AgentAction, Observation
from ..solutions import SOLUTIONS, has_solution
from . import protocol
from .budget import BudgetGuard
from .cache import ResponseCache
from .client import FakeLLMClient, LLMClient, LLMMessage, LLMRequest
from .pricing import DEFAULT_MODEL

#: Default budget (USD) for the offline path, where calls are free but still
#: priced for accounting. Generous relative to the cent-scale example tasks.
DEFAULT_OFFLINE_BUDGET_USD = 1.0


@dataclass(frozen=True)
class LLMAgentConfig:
    """Sampling/identity knobs for an :class:`LLMAgent`."""

    model: str = DEFAULT_MODEL
    max_tokens: int = 1024
    temperature: float = 0.0
    name: str = "llm"


class LLMAgent(Agent):
    """Drive a task by asking an :class:`LLMClient` for one action per step."""

    name = "llm"

    def __init__(
        self,
        client: LLMClient,
        *,
        budget: BudgetGuard,
        tool_specs: Sequence[ToolSpec],
        config: LLMAgentConfig | None = None,
        cache: ResponseCache | None = None,
        redact_transcript: bool = True,
    ) -> None:
        self._client = client
        self._budget = budget
        self._specs = tuple(tool_specs)
        self._config = config or LLMAgentConfig()
        self._cache = cache
        self._redact = redact_transcript
        self.name = self._config.name
        self._task: Task | None = None
        self._system = ""
        self._messages: list[LLMMessage] = []
        self._finished = False
        self._redactions = 0

    # -- agent protocol -----------------------------------------------------

    def reset(self, task: Task) -> None:
        self._task = task
        self._system = protocol.build_system_prompt(task, self._specs)
        self._messages = []
        self._finished = False
        self._redactions = 0

    def propose(self, observation: Observation) -> AgentAction:
        if self._finished:
            return AgentAction.finish("llm agent already finished")
        if observation.step == 0:
            user = protocol.render_task_message(observation.task, self._specs)
        else:
            user = protocol.render_step_message(observation)
        self._append("user", user)

        request = LLMRequest(
            model=self._config.model,
            system=self._system,
            messages=tuple(self._messages),
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

        response = self._cache.get(request) if self._cache is not None else None
        if response is None:
            # Hard pre-call stop: the guard prices the worst case and may refuse
            # (BudgetExceeded / BudgetUnpriced) before we ever contact the client.
            self._budget.check(request)
            response = self._client.complete(request)
            self._budget.record(response)
            if self._cache is not None:
                self._cache.put(request, response)
        else:
            self._budget.record(response)  # cached ⇒ free; keeps totals honest

        self._append("assistant", response.text)
        try:
            action = protocol.parse_action(response.text)
        except protocol.ActionParseError as exc:
            self._finished = True
            return AgentAction.finish(f"llm reply could not be parsed: {exc}")
        if action.is_finish:
            self._finished = True
        return action

    # -- introspection ------------------------------------------------------

    def _append(self, role: str, content: str) -> None:
        if self._redact:
            content, n = redact_text(content)
            self._redactions += n
        self._messages.append(LLMMessage(role, content or ""))

    def transcript(self) -> list[dict[str, str]]:
        """The conversation as stored (already redacted when redaction is on)."""
        return [m.to_dict() for m in self._messages]

    def usage(self) -> dict[str, Any]:
        """Budget totals, cache stats, and redaction count for this agent."""
        return {
            "model": self._config.model,
            "client": self._client.name,
            "requires_network": self._client.requires_network,
            "budget": self._budget.to_dict(),
            "cache": self._cache.stats() if self._cache is not None else None,
            "transcript_redactions": self._redactions,
        }


# --- construction helpers --------------------------------------------------


def _specs_for_task(task: Task, registry: Any = None) -> list[ToolSpec]:
    """Tool specs offered to the agent: the task's allowed tools, else all of them."""
    registry = registry or build_registry()
    allowed = set(task.allowed_tools)
    specs = [s for s in registry.specs() if s.name in allowed]
    return specs or registry.specs()


def build_llm_agent(
    task: Task,
    client: LLMClient,
    *,
    budget: BudgetGuard,
    config: LLMAgentConfig | None = None,
    cache: ResponseCache | None = None,
    redact_transcript: bool = True,
    registry: Any = None,
) -> LLMAgent:
    """Construct an :class:`LLMAgent` for ``task`` driven by ``client``."""
    return LLMAgent(
        client,
        budget=budget,
        tool_specs=_specs_for_task(task, registry),
        config=config,
        cache=cache,
        redact_transcript=redact_transcript,
    )


def build_fake_llm_agent(
    task: Task,
    *,
    budget: BudgetGuard | None = None,
    config: LLMAgentConfig | None = None,
    cache: ResponseCache | None = None,
    redact_transcript: bool = True,
    registry: Any = None,
) -> LLMAgent:
    """Build an **offline** LLM agent that solves ``task`` via a scripted fake.

    The fake client replays the task's known-good solution
    (:data:`~code_agent_runtime.agents.solutions.SOLUTIONS`) as protocol JSON
    actions, then finishes — so the entire model-backed path (prompt → parse →
    action → tool → score) runs end to end with no network and no API key, while
    still exercising the budget guard, cache, and redaction. Raises
    :class:`KeyError` (with the available ids) for a task that has no solution,
    mirroring the scripted agent.
    """
    try:
        builder = SOLUTIONS[task.id]
    except KeyError:
        available = ", ".join(sorted(SOLUTIONS)) or "none"
        raise KeyError(
            f"no built-in fake LLM solution for task {task.id!r} (available: {available})"
        ) from None
    if not has_solution(task.id):  # pragma: no cover - defensive, mirrors SOLUTIONS
        raise KeyError(task.id)
    calls = builder(task)
    responses = [protocol.action_json(c) for c in calls]
    responses.append(protocol.finish_json("solution complete"))
    client = FakeLLMClient(responses)
    budget = budget or BudgetGuard(max_cost_usd=DEFAULT_OFFLINE_BUDGET_USD)
    return build_llm_agent(
        task,
        client,
        budget=budget,
        config=config,
        cache=cache,
        redact_transcript=redact_transcript,
        registry=registry,
    )


def dry_run_plan(
    task: Task,
    *,
    config: LLMAgentConfig | None = None,
    budget: BudgetGuard | None = None,
    registry: Any = None,
) -> dict[str, Any]:
    """Describe the *first* real request for ``task`` and its cost — no call made.

    Builds the exact system prompt and first user turn the agent would send,
    estimates the call's input tokens, and asks the budget guard to price the
    worst case. Makes **zero** client calls and spends nothing, so it is the safe
    way to preview a paid run (model, prompt, and a per-call cost bound). If the
    model is unpriced the cost fields are ``None`` and ``priced`` is ``False``
    rather than raising.
    """
    config = config or LLMAgentConfig()
    specs = _specs_for_task(task, registry)
    system = protocol.build_system_prompt(task, specs)
    first_user = protocol.render_task_message(task, specs)
    request = LLMRequest(
        model=config.model,
        system=system,
        messages=(LLMMessage("user", first_user),),
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    budget = budget or BudgetGuard(max_cost_usd=DEFAULT_OFFLINE_BUDGET_USD)

    plan: dict[str, Any] = {
        "task_id": task.id,
        "model": config.model,
        "max_tokens": config.max_tokens,
        "estimated_input_tokens": request.estimated_input_tokens(),
        "system_prompt": system,
        "first_user_message": first_user,
        "budget": budget.to_dict(),
        "priced": True,
        "worst_case_first_call_usd": None,
    }
    from .budget import BudgetUnpriced

    try:
        plan["worst_case_first_call_usd"] = round(budget.check(request), 6)
    except BudgetUnpriced as exc:
        plan["priced"] = False
        plan["price_note"] = str(exc)
    return plan
