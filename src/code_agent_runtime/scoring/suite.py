"""Eval suite runner and result schema (Milestone 8).

A *suite* runs a set of tasks across a set of agents and collects one
:class:`EvalRecord` per run — the row the plan's result table needs: task id,
agent, pass/fail, runtime, tool-call count, command count, and a failure reason.
The whole thing is a :class:`SuiteResult` that serialises to JSON, so a run can be
reported (see :mod:`code_agent_runtime.reports`) and later compared
(regression analysis, Milestone 9).

Two deliberate choices:

- **Wall-clock timing lives here, not in the run.** A :class:`RunResult` is
  timing-free and deterministic by design; the suite layer is where wall-clock
  belongs, so this module times each ``run_task`` call. The clock is injectable
  for deterministic tests.
- **The agent/task matrix skips the inapplicable.** ``scripted`` only runs where a
  built-in solution exists and ``probe`` only where an adversarial probe exists;
  inapplicable pairs are recorded under ``skipped`` rather than failed, so the
  report distinguishes "did not solve" from "was not attempted".

This module imports the runtime lazily (inside the functions that need it) so
``scoring`` stays importable from the runtime without an import cycle.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agents import (
    Agent,
    MockAgent,
    build_scripted_agent,
    build_unsafe_probe_agent,
    has_probe,
    has_solution,
)
from ..tasks import Task
from .scorer import Outcome

#: Result-file schema version; bumped on breaking changes to the on-disk shape.
SCHEMA_VERSION = 1

#: The agents a default suite attempts on every task (inapplicable pairs skip).
DEFAULT_AGENTS: tuple[str, ...] = ("mock", "scripted", "probe")


def build_agent(name: str, task: Task) -> Agent | None:
    """Build the named deterministic agent for ``task``, or ``None`` if N/A.

    ``mock`` always applies. ``scripted`` applies only when a built-in solution
    exists for the task; ``probe`` only when an adversarial probe exists. Returning
    ``None`` lets the suite record the pair as skipped rather than as a failure.
    """
    if name == "mock":
        return MockAgent()
    if name == "scripted":
        return build_scripted_agent(task) if has_solution(task.id) else None
    if name == "probe":
        return build_unsafe_probe_agent(task) if has_probe(task.id) else None
    raise ValueError(f"unknown agent {name!r} (choose from: mock, scripted, probe)")


@dataclass(frozen=True)
class EvalRecord:
    """One row of a suite result: the outcome and effort signals for one run."""

    task_id: str
    agent: str
    outcome: str
    passed: bool | None
    runtime_seconds: float
    tool_call_count: int
    command_count: int
    blocked_count: int
    phase_reached: str
    stop_reason: str
    failure_reason: str | None
    score: Mapping[str, Any]
    trace_path: str | None = None

    @classmethod
    def from_result(
        cls, result: Any, *, runtime_seconds: float, trace_path: str | None = None
    ) -> "EvalRecord":
        """Build a record from a :class:`RunResult` and a measured wall-clock time."""
        blocked = sum(1 for s in result.steps if s.action_kind == "tool" and not s.allowed)
        failure_reason: str | None = None
        if result.outcome == Outcome.FAILED:
            failure_reason = result.score.get("detail") or result.stop_reason
        elif result.outcome == Outcome.ERROR:
            failure_reason = result.error or result.score.get("detail") or result.stop_reason
        return cls(
            task_id=result.task_id,
            agent=result.agent,
            outcome=result.outcome,
            passed=result.score.get("passed"),
            runtime_seconds=round(float(runtime_seconds), 4),
            tool_call_count=result.tool_call_count,
            command_count=result.command_count,
            blocked_count=blocked,
            phase_reached=result.phase_reached,
            stop_reason=result.stop_reason,
            failure_reason=failure_reason,
            score=dict(result.score),
            trace_path=trace_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "outcome": self.outcome,
            "passed": self.passed,
            "runtime_seconds": self.runtime_seconds,
            "tool_call_count": self.tool_call_count,
            "command_count": self.command_count,
            "blocked_count": self.blocked_count,
            "phase_reached": self.phase_reached,
            "stop_reason": self.stop_reason,
            "failure_reason": self.failure_reason,
            "score": dict(self.score),
            "trace_path": self.trace_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvalRecord":
        return cls(
            task_id=data["task_id"],
            agent=data["agent"],
            outcome=data["outcome"],
            passed=data.get("passed"),
            runtime_seconds=float(data.get("runtime_seconds", 0.0)),
            tool_call_count=int(data.get("tool_call_count", 0)),
            command_count=int(data.get("command_count", 0)),
            blocked_count=int(data.get("blocked_count", 0)),
            phase_reached=data.get("phase_reached", ""),
            stop_reason=data.get("stop_reason", ""),
            failure_reason=data.get("failure_reason"),
            score=dict(data.get("score", {})),
            trace_path=data.get("trace_path"),
        )


@dataclass(frozen=True)
class SuiteResult:
    """The result of running a suite: the per-run records plus what was skipped."""

    records: tuple[EvalRecord, ...]
    skipped: tuple[Mapping[str, str], ...] = ()
    label: str | None = None
    schema_version: int = SCHEMA_VERSION

    @property
    def total(self) -> int:
        return len(self.records)

    def totals(self) -> dict[str, int]:
        """Count records by outcome (passed/failed/not_scored/error)."""
        counts = {Outcome.PASSED: 0, Outcome.FAILED: 0, Outcome.NOT_SCORED: 0, Outcome.ERROR: 0}
        for r in self.records:
            counts[r.outcome] = counts.get(r.outcome, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "label": self.label,
            "totals": {"total": self.total, **self.totals()},
            "records": [r.to_dict() for r in self.records],
            "skipped": [dict(s) for s in self.skipped],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SuiteResult":
        return cls(
            records=tuple(EvalRecord.from_dict(r) for r in data.get("records", [])),
            skipped=tuple(dict(s) for s in data.get("skipped", [])),
            label=data.get("label"),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )


def run_suite(
    tasks: Sequence[Task],
    agents: Sequence[str] = DEFAULT_AGENTS,
    *,
    config: Any = None,
    registry: Any = None,
    clock: Callable[[], float] | None = None,
    label: str | None = None,
) -> SuiteResult:
    """Run every applicable (task, agent) pair and collect a :class:`SuiteResult`.

    ``clock`` (default :func:`time.perf_counter`) is injectable so tests can make
    ``runtime_seconds`` deterministic. ``config`` is a
    :class:`~code_agent_runtime.runtime.RunConfig` (defaulted lazily); ``registry``
    is built once and reused across runs.
    """
    from ..runtime import RunConfig, run_task  # lazy: avoids the runtime→scoring cycle
    from ..tools import build_registry

    clock = clock or time.perf_counter
    config = config or RunConfig()
    registry = registry or build_registry()

    records: list[EvalRecord] = []
    skipped: list[Mapping[str, str]] = []
    for task in tasks:
        for name in agents:
            agent = build_agent(name, task)
            if agent is None:
                skipped.append({"task_id": task.id, "agent": name})
                continue
            start = clock()
            result = run_task(task, agent, config=config, registry=registry)
            elapsed = clock() - start
            records.append(EvalRecord.from_result(result, runtime_seconds=elapsed))
    return SuiteResult(records=tuple(records), skipped=tuple(skipped), label=label)


def write_suite_result(suite: SuiteResult, path: str | Path) -> Path:
    """Write ``suite`` to ``path`` as JSON (creating parent directories)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(suite.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def load_suite_result(path: str | Path) -> SuiteResult:
    """Load a :class:`SuiteResult` previously written by :func:`write_suite_result`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SuiteResult.from_dict(data)
