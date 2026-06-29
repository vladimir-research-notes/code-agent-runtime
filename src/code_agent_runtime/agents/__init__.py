"""Agents that drive the runtime loop (Milestone 4).

An agent decides what to do next; the runtime owns every side effect. This
milestone ships the two deterministic, model-free baselines required by the
plan:

- :class:`MockAgent` — the null baseline: no actions, finishes immediately.
- :class:`ScriptedAgent` — replays a fixed plan, then finishes.

Built-in scripted plans that solve the shipped example tasks live in
:mod:`.solutions` (:func:`build_scripted_agent`, :func:`has_solution`). Optional
LLM-backed agents are added, cost-guarded and disabled by default, in later
milestones (see ``docs/PLAN.md``).
"""

from __future__ import annotations

from .base import Agent, AgentAction, Observation
from .mock_agent import MockAgent
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
]
