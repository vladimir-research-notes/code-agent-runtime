"""``mock`` — the null baseline agent (Milestone 4).

The mock agent performs **no** tool calls and finishes immediately. It is a
deliberate control, not a solver: it establishes the floor of the eval harness
(a task that the null agent "passes" is a task whose fixture already passes its
own tests) and it exercises the whole runtime pipeline — workspace preparation,
the empty agent loop, test execution, scoring, and reporting — without any model,
network, or filesystem mutation. Its behaviour does not depend on the task, so
every run of it is byte-for-byte reproducible.
"""

from __future__ import annotations

from .base import Agent, AgentAction, Observation


class MockAgent(Agent):
    """An agent that does nothing and finishes (deterministic null baseline)."""

    name = "mock"

    def propose(self, observation: Observation) -> AgentAction:
        return AgentAction.finish("mock agent performs no actions (null baseline)")
