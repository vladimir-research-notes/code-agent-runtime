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
(:func:`build_unsafe_probe_agent`, :func:`has_probe`). Optional LLM-backed agents
are added, cost-guarded and disabled by default, in later milestones (see
``docs/PLAN.md``).
"""

from __future__ import annotations

from .base import Agent, AgentAction, Observation
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
]
