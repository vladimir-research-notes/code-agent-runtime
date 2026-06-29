"""Run state: phases, outcomes, and the structured run record (Milestone 4).

These types are the runtime's vocabulary and its output. They are pure data —
nothing here prepares a workspace, dispatches a tool, or runs a command (that is
:mod:`.execution` and :mod:`.agent_loop`). Keeping them separate means the
(future) trace recorder (Milestone 5), scorer (Milestone 8), and reports can
consume a :class:`RunResult` without importing the execution machinery.

Two closed vocabularies anchor the state machine:

- :class:`RunPhase` — the stage a run reached. The loop advances through them in
  order; on an unexpected error it stops at whichever phase was current.
- :class:`RunOutcome` — the scored verdict for the run.

Following the tools' convention, results carry **no wall-clock timing**:
timestamps and durations belong to the trace recorder, and leaving them out
keeps a :class:`RunResult` deterministic and unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from ..tools import ToolResult
from ..tools.base import DEFAULT_TOOL_TIMEOUT_SECONDS


class RunPhase:
    """The stages a run moves through, in order."""

    PREPARING: ClassVar[str] = "preparing_workspace"
    AGENT_LOOP: ClassVar[str] = "agent_loop"
    TESTING: ClassVar[str] = "testing"
    CAPTURING_DIFF: ClassVar[str] = "capturing_diff"
    SCORING: ClassVar[str] = "scoring"
    REPORTING: ClassVar[str] = "reporting"
    DONE: ClassVar[str] = "done"
    ERROR: ClassVar[str] = "error"

    ALL: ClassVar[frozenset[str]] = frozenset(
        {PREPARING, AGENT_LOOP, TESTING, CAPTURING_DIFF, SCORING, REPORTING, DONE, ERROR}
    )


class RunOutcome:
    """The scored verdict for a run."""

    PASSED: ClassVar[str] = "passed"
    FAILED: ClassVar[str] = "failed"
    #: Scoring method ``none`` (or one deferred to a later milestone): the run
    #: completed but is not automatically judged pass/fail.
    NOT_SCORED: ClassVar[str] = "not_scored"
    #: The run could not complete (e.g. workspace preparation failed).
    ERROR: ClassVar[str] = "error"

    ALL: ClassVar[frozenset[str]] = frozenset({PASSED, FAILED, NOT_SCORED, ERROR})


@dataclass(frozen=True)
class RunConfig:
    """Knobs for a single run. Defaults are safe for the CPU-only example tasks."""

    #: Hard cap on agent steps, so a misbehaving agent cannot loop forever.
    max_steps: int = 50
    #: Per-tool wall-clock budget passed to the :class:`ToolContext`.
    tool_timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS
    #: Run the task's test command after the agent loop (when the task has one).
    run_tests: bool = True
    #: ``git init`` the prepared workspace so the final diff can be captured.
    init_git: bool = True
    #: Keep the ephemeral workspace on disk after the run (for inspection).
    keep_workspace: bool = False


@dataclass(frozen=True)
class StepRecord:
    """One step of the agent loop: the action and (for a tool action) its result.

    ``allowed`` records whether the tool was permitted by the task's
    ``allowed_tools``; a blocked call has ``allowed=False`` and a failed result
    that was synthesised by the runtime rather than produced by the tool.
    """

    index: int
    action_kind: str
    tool: str | None
    args: Mapping[str, Any]
    result: ToolResult | None
    allowed: bool
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "action_kind": self.action_kind,
            "tool": self.tool,
            "args": dict(self.args),
            "allowed": self.allowed,
            "message": self.message,
            "result": self.result.to_dict() if self.result is not None else None,
        }


@dataclass(frozen=True)
class RunResult:
    """The structured outcome of one run — the runtime's single return value.

    Carries everything a report or the (future) trace recorder needs: the
    agent's steps, the test result, the final diff, the score, and the counts the
    eval report (Milestone 8) tabulates (``tool_call_count``, ``command_count``).
    """

    task_id: str
    agent: str
    outcome: str
    phase_reached: str
    stop_reason: str
    steps: tuple[StepRecord, ...]
    tool_call_count: int
    command_count: int
    score: Mapping[str, Any]
    tests: Mapping[str, Any] | None = None
    diff: Mapping[str, Any] | None = None
    workspace: str | None = None
    kept_workspace: bool = False
    git: bool = False
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.outcome == RunOutcome.PASSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "outcome": self.outcome,
            "phase_reached": self.phase_reached,
            "stop_reason": self.stop_reason,
            "tool_call_count": self.tool_call_count,
            "command_count": self.command_count,
            "score": dict(self.score),
            "tests": dict(self.tests) if self.tests is not None else None,
            "diff": dict(self.diff) if self.diff is not None else None,
            "workspace": self.workspace,
            "kept_workspace": self.kept_workspace,
            "git": self.git,
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps],
        }
