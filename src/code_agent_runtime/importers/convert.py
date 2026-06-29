"""Convert an imported run into a scored, replayable runtime artifact (Milestone 11).

This is where an external record (:class:`ImportedRun`) becomes a first-class
citizen of this runtime: a :class:`~code_agent_runtime.runtime.state.RunResult`
scored by the **same** scorer as a native run, and a
:class:`~code_agent_runtime.traces.schema.Trace` the existing replay/report tools
read unchanged. One function, :func:`import_to_run`, does it; it returns an
:class:`ImportOutcome` carrying both plus how the run was scored.

There are two scoring modes, and the difference is the whole point of the
milestone:

- **trust** — score against the diff and the *declared* test result the source
  carried. Fast, but it believes the source. The only option when the import has
  no file content (a diff-only or transcript-only run).
- **verify** — reconstruct the workspace by materialising the imported after-state
  over the task's fixture, then run the task's **real** test command and capture a
  **real** git diff through this runtime's own tools, and score *that*. This turns
  "the external agent said its tests passed" into "this runtime ran the tests and
  they passed." It needs the after-state (``imported.files``) and a resolvable
  fixture.

``mode="auto"`` (the default) verifies when it can and falls back to trust
otherwise, recording which happened on the outcome so a report never overstates
its evidence. The imported *process* (the external tool calls) is preserved as the
trace's steps in both modes; only the *evidence* differs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..runtime.state import RunConfig, RunOutcome, RunPhase, RunResult, StepRecord
from ..scoring import score_run
from ..tasks import Task, resolve_fixture
from ..tools import ToolResult, build_registry
from ..traces import Clock, TraceRecorder
from ..traces.schema import Trace
from .schema import TOOL_CATEGORY, ImportedRun, ImportSourceError

#: Tool names whose execution counts as "running a command", mirroring
#: ``runtime.agent_loop._COMMAND_TOOLS`` so imported counts agree with native ones.
_COMMAND_TOOLS = frozenset({"run_shell", "run_tests"})


@dataclass(frozen=True)
class ImportOutcome:
    """The result of importing one external run.

    ``result`` and ``trace`` are exactly what a native run produces (scored by the
    same scorer, replayable by the same tools). ``verified`` says whether the
    verdict came from re-running the test command (``True``) or from trusting the
    source's declared evidence (``False``); ``mode`` is the requested mode and
    ``note`` explains any fallback.
    """

    result: RunResult
    trace: Trace
    verified: bool
    mode: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "mode": self.mode,
            "note": self.note,
            "result": self.result.to_dict(),
            "trace_id": self.trace.trace_id,
        }


def can_verify(imported: ImportedRun, task: Task) -> bool:
    """True if ``imported`` can be verified against ``task`` (after-state + fixture)."""
    if not imported.has_after_state:
        return False
    try:
        return Path(resolve_fixture(task)).exists()
    except Exception:  # pragma: no cover - defensive: a malformed fixture path
        return False


def import_to_run(
    imported: ImportedRun,
    task: Task,
    *,
    mode: str = "auto",
    config: RunConfig | None = None,
    registry: Any = None,
    clock: Clock | None = None,
    trace_id: str | None = None,
) -> ImportOutcome:
    """Convert ``imported`` into a scored :class:`RunResult` and a :class:`Trace`.

    ``mode`` is ``"auto"`` (verify if possible, else trust), ``"verify"`` (require
    verification — raise if the after-state or fixture is missing), or ``"trust"``
    (always trust the declared evidence). ``clock``/``trace_id`` are injectable so a
    test can make the produced trace fully deterministic.
    """
    if mode not in ("auto", "verify", "trust"):
        raise ValueError(f"unknown import mode {mode!r} (choose from: auto, verify, trust)")
    config = config or RunConfig()
    registry = registry or build_registry()

    feasible = can_verify(imported, task)
    if mode == "verify" and not feasible:
        why = "no after-state file content in the import" if not imported.has_after_state else (
            f"fixture for task {task.id!r} is unavailable"
        )
        raise ImportSourceError([f"cannot verify this import: {why}"])

    verified = mode == "verify" or (mode == "auto" and feasible)
    note = _mode_note(mode, verified, imported)

    steps = _steps_from_actions(imported)
    stop_reason = _stop_reason(imported)

    workspace = None
    try:
        if verified:
            workspace, tests, diff = _materialize_and_measure(task, imported, config, registry)
        else:
            tests = dict(imported.tests) if imported.tests is not None else None
            diff = dict(imported.diff) if imported.diff is not None else None

        workspace_root = Path(workspace.root) if workspace is not None else None
        score = score_run(task, tests=tests, diff=diff, workspace=workspace_root).to_dict()

        result = _build_result(
            task=task,
            imported=imported,
            steps=steps,
            score=score,
            tests=tests,
            diff=diff,
            stop_reason=stop_reason,
            workspace=workspace,
        )
        trace = _build_trace(
            task=task,
            imported=imported,
            result=result,
            steps=steps,
            score=score,
            tests=tests,
            diff=diff,
            config=config,
            workspace=workspace,
            clock=clock,
            trace_id=trace_id,
        )
        return ImportOutcome(result=result, trace=trace, verified=verified, mode=mode, note=note)
    finally:
        if workspace is not None:
            workspace.cleanup()


# -- evidence ---------------------------------------------------------------


def _materialize_and_measure(
    task: Task, imported: ImportedRun, config: RunConfig, registry: Any
):
    """Reconstruct the workspace from the after-state and measure it for real.

    Prepares the task's fixture as the baseline (a git commit, when git is
    available), overlays the imported after-state, then runs the task's test
    command and captures the git diff with this runtime's own tools — so the
    verdict is this runtime's measurement, not the source's claim. Returns
    ``(workspace, tests_data, diff_data)``; the caller owns cleanup.
    """
    from ..runtime import prepare_workspace
    from ..runtime.execution import make_context

    workspace = prepare_workspace(task, init_git=config.init_git)
    for rel, content in imported.files.items():
        target = workspace.root / rel
        if content is None:
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    ctx = make_context(task, workspace, tool_timeout_seconds=config.tool_timeout_seconds)

    tests_data = None
    if config.run_tests and task.test_command is not None:
        tr = registry.get("run_tests").run(
            ctx, command=list(task.test_command), timeout_seconds=config.tool_timeout_seconds
        )
        tests_data = tr.data

    diff_data = None
    if workspace.git:
        dr = registry.get("git_diff").run(ctx)
        if dr.ok:
            diff_data = dr.data

    return workspace, tests_data, diff_data


# -- steps & result ---------------------------------------------------------


def _steps_from_actions(imported: ImportedRun) -> list[StepRecord]:
    """Synthesise runtime :class:`StepRecord`s from the imported action stream.

    ``tool_call`` and ``finish`` actions become steps (so counts and the timeline
    match a native run); bare ``message`` actions are kept only in the imported
    record, not replayed as steps. Each tool step carries a fabricated
    :class:`ToolResult` echoing the imported summary, so the trace reads faithfully.
    """
    steps: list[StepRecord] = []
    for action in imported.actions:
        if action.kind == "finish":
            steps.append(
                StepRecord(
                    index=len(steps),
                    action_kind="finish",
                    tool=None,
                    args={},
                    result=None,
                    allowed=True,
                    message=action.summary,
                )
            )
        elif action.kind == "tool_call":
            tool = action.tool or action.raw_tool or "unknown"
            ok = action.data.get("ok")
            res = ToolResult(
                tool=tool,
                category=TOOL_CATEGORY.get(tool, "read"),
                ok=bool(ok) if ok is not None else True,
                summary=action.summary,
                data=dict(action.data),
                error=action.data.get("error"),
            )
            steps.append(
                StepRecord(
                    index=len(steps),
                    action_kind="tool",
                    tool=tool,
                    args=dict(action.args),
                    result=res,
                    allowed=bool(action.data.get("allowed", True)),
                    message=None,
                )
            )
        # message actions are not runtime steps; they live in the imported record.
    return steps


def _counts(steps: list[StepRecord]) -> tuple[int, int]:
    tool_calls = sum(1 for s in steps if s.action_kind == "tool")
    commands = sum(1 for s in steps if s.tool in _COMMAND_TOOLS and s.allowed)
    return tool_calls, commands


def _stop_reason(imported: ImportedRun) -> str:
    for action in imported.actions:
        if action.kind == "finish":
            return action.summary or "imported run finished"
    return "imported run (no explicit finish)"


def _build_result(
    *,
    task: Task,
    imported: ImportedRun,
    steps: list[StepRecord],
    score: dict[str, Any],
    tests: Any,
    diff: Any,
    stop_reason: str,
    workspace: Any,
) -> RunResult:
    tool_calls, commands = _counts(steps)
    return RunResult(
        task_id=task.id,
        agent=imported.agent_label,
        outcome=score["outcome"],
        phase_reached=RunPhase.DONE,
        stop_reason=stop_reason,
        steps=tuple(steps),
        tool_call_count=tool_calls,
        command_count=commands,
        score=score,
        tests=tests,
        diff=diff,
        workspace=str(workspace.root) if workspace is not None else None,
        kept_workspace=False,
        git=workspace.git if workspace is not None else False,
        error=None,
        policy=None,
    )


# -- trace ------------------------------------------------------------------


def _build_trace(
    *,
    task: Task,
    imported: ImportedRun,
    result: RunResult,
    steps: list[StepRecord],
    score: dict[str, Any],
    tests: Any,
    diff: Any,
    config: RunConfig,
    workspace: Any,
    clock: Clock | None,
    trace_id: str | None,
) -> Trace:
    """Drive a :class:`TraceRecorder` over the imported run to build a canonical Trace.

    Uses the same recorder the runtime uses, so the produced trace is byte-for-byte
    the same shape as a native one and replays identically. Fabricated
    :class:`ToolResult`s for the tests/diff events carry the imported (or verified)
    evidence. The trace records the source kind under ``config`` so an inspector can
    see this run was imported, not natively executed.
    """
    recorder = TraceRecorder(clock=clock, trace_id=trace_id)
    # Tag the run's config echo with import provenance (config is asdict-ed by the
    # recorder; we cannot add keys, so provenance rides in the trace via the agent
    # label and the source-kind summary on the finish step instead).
    recorder.start(task=task, agent=imported.agent_label, config=config)
    if workspace is not None:
        recorder.workspace_prepared(workspace)
    for step in steps:
        recorder.agent_step(step)
    if tests is not None:
        recorder.tests_ran(_tests_result(tests))
    if diff is not None:
        recorder.diff_captured(_diff_result(diff))
    recorder.scored(score)
    return recorder.finish(result)


def _tests_result(tests: dict[str, Any]) -> ToolResult:
    passed = bool(tests.get("passed"))
    if tests.get("timed_out"):
        summary = "tests timed out"
    else:
        summary = "tests passed" if passed else f"tests failed (exit {tests.get('exit_code')})"
    return ToolResult(
        tool="run_tests", category="exec", ok=passed, summary=summary, data=dict(tests)
    )


def _diff_result(diff: dict[str, Any]) -> ToolResult:
    files = diff.get("files", [])
    untracked = diff.get("untracked", [])
    summary = (
        f"{len(files) + len(untracked)} file(s) changed, "
        f"+{diff.get('insertions', 0)}/-{diff.get('deletions', 0)}"
    )
    return ToolResult(tool="git_diff", category="read", ok=True, summary=summary, data=dict(diff))


def _mode_note(mode: str, verified: bool, imported: ImportedRun) -> str:
    if verified:
        return "verified: re-ran the task's test command against the reconstructed workspace"
    if mode == "trust":
        return "trust: scored against the source's declared diff/test result (not re-run)"
    # auto, fell back to trust
    if not imported.has_after_state:
        return (
            "trust (auto): the import carried no after-state file content, so the test "
            "command could not be re-run; scored against the declared evidence"
        )
    return "trust (auto): the task fixture was unavailable, so the run could not be verified"
