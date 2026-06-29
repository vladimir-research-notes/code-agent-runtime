"""Agents that drive the runtime loop (Milestone 4).

An agent decides what to do next; the runtime owns every side effect. This
milestone ships the two deterministic, model-free baselines required by the
plan:

- :class:`MockAgent` — the null baseline: no actions, finishes immediately.
- :class:`ScriptedAgent` — replays a fixed plan, then finishes.

Built-in scripted plans that solve the shipped example tasks live in
:mod:`.solutions` (:func:`build_scripted_agent`, :func:`has_solution`).
Adversarial *probe* scripts that deliberately attempt host-escaping actions, so
the Milestone 7 sandbox can be observed refusing them, live in :mod:`.probes`
(:func:`build_unsafe_probe_agent`, :func:`has_probe`).

The optional, cost-guarded LLM-backed agent (Milestone 10) lives in the
:mod:`.llm` subpackage. It is **disabled by default**: it requires an explicitly
constructed client and budget, never appears in the default eval matrix, and its
real provider lazily imports ``anthropic`` only when actually used.
:class:`LLMAgent` and :func:`build_fake_llm_agent` (an offline, no-API-key path
that solves the example tasks through the model wire format) are re-exported here
for convenience; the full surface lives in :mod:`code_agent_runtime.agents.llm`.
"""

from __future__ import annotations

from .base import Agent, AgentAction, Observation
from .llm import (
    DEFAULT_MODEL,
    BudgetError,
    BudgetExceeded,
    BudgetGuard,
    BudgetUnpriced,
    FakeLLMClient,
    LLMAgent,
    LLMAgentConfig,
    LLMClient,
    LLMClientError,
    ResponseCache,
    build_claude_client,
    build_fake_llm_agent,
    build_llm_agent,
    dry_run_plan,
)
from .mock_agent import MockAgent
from .probes import PROBES, build_unsafe_probe_agent, has_probe
from .scripted_agent import ScriptedAgent
from .solutions import SOLUTIONS, build_scripted_agent, has_solution

__all__ = [
    "Agent",
    "AgentAction",
    "Observation",
    "MockAgent",
    "ScriptedAgent",
    "build_scripted_agent",
    "has_solution",
    "SOLUTIONS",
    "build_unsafe_probe_agent",
    "has_probe",
    "PROBES",
    # Optional cost-controlled LLM adapter (Milestone 10).
    "LLMAgent",
    "LLMAgentConfig",
    "LLMClient",
    "LLMClientError",
    "FakeLLMClient",
    "BudgetGuard",
    "BudgetError",
    "BudgetExceeded",
    "BudgetUnpriced",
    "ResponseCache",
    "DEFAULT_MODEL",
    "build_llm_agent",
    "build_fake_llm_agent",
    "build_claude_client",
    "dry_run_plan",
]
