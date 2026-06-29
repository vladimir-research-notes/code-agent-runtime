"""Tests for the Milestone 11 Claude Code trace importer.

CPU-only and offline: no model, no network, no paid API. The importer is
exercised on the shipped example tasks via the deterministic scripted solutions.
Coverage:

- the diff helpers (``tree_diff`` for content maps, ``parse_unified_diff`` for raw
  diff text) produce the ``git_diff``-shaped dict the scorers consume;
- each source builder (``before_after``, ``diff_and_log``, ``transcript``,
  ``synthesize``/``export``) normalises into a valid ``ImportedRun``;
- ``ImportedRun`` JSON round-trips and rejects malformed documents;
- conversion + scoring in both **trust** and **verify** mode, and the round-trip
  invariant (native run → export → import → same verdict);
- verification is a real measurement: a broken change is scored ``failed`` even
  though a trust-mode score of the same declared evidence would pass;
- the produced trace is schema-valid and replays with the existing tooling;
- the ``import`` CLI surface (``synthesize`` / ``before-after`` / ``show`` /
  ``run``).

Tests that need ``git`` skip when it is absent (verify mode's captured diff).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from code_agent_runtime import cli
from code_agent_runtime import importers as I
from code_agent_runtime import runtime as R
from code_agent_runtime import tasks as TK
from code_agent_runtime import traces as TR
from code_agent_runtime.traces.recorder import Clock

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
HAS_GIT = shutil.which("git") is not None

BUGFIX = "bugfix/sum-range-off-by-one"
EXPECTED_FILES = "bugfix/sum-range-expected-files"
DIFF_SCOPE = "refactor/sum-range-diff-scope"

_BUGGY = "    for i in range(1, n):"
_FIXED = "    for i in range(1, n + 1):"


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


class FakeClock(Clock):
    """Deterministic clock so a produced trace's timestamps/ids are assertable."""

    def __init__(self, *, start_wall: float = 1_700_000_000.0) -> None:
        self._wall = start_wall
        self._mono = 0.0

    def wall(self) -> float:
        v = self._wall
        self._wall += 1.0
        return v

    def monotonic(self) -> float:
        v = self._mono
        self._mono += 0.5
        return v


def _fixture_tree(task: TK.Task) -> dict[str, str]:
    return I.read_tree(TK.resolve_fixture(task))


def _before_after_dirs(task: TK.Task, tmp_path: Path, *, fix: str) -> tuple[Path, Path]:
    """Copy the task fixture into before/ and after/, applying ``fix`` to after/."""
    fixture = Path(TK.resolve_fixture(task))
    before = tmp_path / "before"
    after = tmp_path / "after"
    for dest in (before, after):
        shutil.copytree(fixture, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    summ = after / "summation.py"
    summ.write_text(summ.read_text(encoding="utf-8").replace(_BUGGY, fix), encoding="utf-8")
    return before, after


# -- diff helpers -----------------------------------------------------------


def test_tree_diff_counts_modifications() -> None:
    before = {"a.py": "x = 1\ny = 2\n"}
    after = {"a.py": "x = 1\ny = 3\n"}
    diff = I.tree_diff(before, after)
    assert diff["insertions"] == 1 and diff["deletions"] == 1
    assert [f["path"] for f in diff["files"]] == ["a.py"]
    assert "diff --git a/a.py b/a.py" in diff["diff"]


def test_tree_diff_added_and_deleted_files() -> None:
    diff = I.tree_diff({"gone.py": "a\nb\n"}, {"new.py": "1\n2\n3\n"})
    by_path = {f["path"]: f for f in diff["files"]}
    assert by_path["new.py"]["insertions"] == 3 and by_path["new.py"]["deletions"] == 0
    assert by_path["gone.py"]["insertions"] == 0 and by_path["gone.py"]["deletions"] == 2


def test_tree_diff_ignores_unchanged() -> None:
    diff = I.tree_diff({"a.py": "same\n"}, {"a.py": "same\n"})
    assert diff["files"] == [] and diff["insertions"] == 0 and diff["deletions"] == 0


def test_parse_unified_diff_counts_and_paths() -> None:
    text = (
        "diff --git a/summation.py b/summation.py\n"
        "--- a/summation.py\n"
        "+++ b/summation.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-    for i in range(1, n):\n"
        "+    for i in range(1, n + 1):\n"
    )
    diff = I.parse_unified_diff(text)
    assert [f["path"] for f in diff["files"]] == ["summation.py"]
    assert diff["insertions"] == 1 and diff["deletions"] == 1
    assert diff["untracked"] == []


def test_parse_unified_diff_new_file_is_untracked() -> None:
    text = (
        "diff --git a/new.py b/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+line one\n"
        "+line two\n"
    )
    diff = I.parse_unified_diff(text)
    assert diff["untracked"] == ["new.py"]
    assert diff["insertions"] == 2 and diff["deletions"] == 0


# -- source builders --------------------------------------------------------


def test_import_before_after_builds_after_state(tmp_path: Path) -> None:
    task = _load(BUGFIX)
    before, after = _before_after_dirs(task, tmp_path, fix=_FIXED)
    imported = I.import_before_after(before, after, task_id=task.id)
    assert imported.source_kind == "before_after"
    assert imported.has_after_state
    assert list(imported.files) == ["summation.py"]
    assert _FIXED in imported.files["summation.py"]
    assert imported.diff is not None and imported.diff["insertions"] == 1
    # one edit action + a finish
    assert imported.actions[-1].kind == "finish"
    assert any(a.kind == "tool_call" for a in imported.actions)


def test_import_diff_and_log_detects_test_result() -> None:
    task = _load(BUGFIX)
    text = I.tree_diff({"summation.py": _BUGGY + "\n"}, {"summation.py": _FIXED + "\n"})["diff"]
    imported = I.import_diff_and_log(
        text,
        [{"command": ["python3", "-m", "pytest", "-q"], "exit_code": 0, "is_test": True}],
        task_id=task.id,
        test_command=list(task.test_command),
    )
    assert imported.source_kind == "diff_and_log"
    assert imported.tests is not None and imported.tests["passed"] is True
    assert not imported.has_after_state  # no file content -> trust only
    tools = [a.tool for a in imported.actions if a.kind == "tool_call"]
    assert "run_tests" in tools


def test_import_transcript_maps_tool_names() -> None:
    imported = I.import_transcript(
        [
            {"tool": "Read", "input": {"path": "summation.py"}},
            {"role": "assistant", "content": [{"type": "tool_use", "name": "Edit", "input": {"path": "summation.py"}}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
        ],
        task_id="x/y",
    )
    tool_calls = [a for a in imported.actions if a.kind == "tool_call"]
    assert [a.tool for a in tool_calls] == ["read_file", "apply_patch"]
    assert [a.raw_tool for a in tool_calls] == ["Read", "Edit"]
    assert any(a.kind == "message" for a in imported.actions)
    assert imported.actions[-1].kind == "finish"


def test_synthesize_import_is_self_contained() -> None:
    task = _load(BUGFIX)
    imported = I.synthesize_import(task)
    assert imported.source_kind == "synthetic"
    assert imported.task_id == task.id
    assert imported.has_after_state
    assert _FIXED in imported.files["summation.py"]
    # The scripted solution's three tool calls survive the export.
    tools = [a.tool for a in imported.actions if a.kind == "tool_call"]
    assert tools == ["read_file", "search_repo", "apply_patch"]


# -- schema round-trip / validation -----------------------------------------


def test_imported_run_round_trips() -> None:
    imported = I.synthesize_import(_load(BUGFIX))
    again = I.ImportedRun.from_dict(imported.to_dict())
    assert again.to_dict() == imported.to_dict()


def test_imported_run_rejects_unknown_source_kind() -> None:
    with pytest.raises(I.ImportSourceError) as exc:
        I.ImportedRun.from_dict({"source_kind": "nonsense", "actions": []})
    assert any("source_kind" in p for p in exc.value.problems)


def test_imported_run_rejects_bad_files_value() -> None:
    with pytest.raises(I.ImportSourceError):
        I.ImportedRun.from_dict(
            {"source_kind": "transcript", "actions": [], "files": {"a.py": 123}}
        )


def test_load_import_source_round_trips(tmp_path: Path) -> None:
    imported = I.synthesize_import(_load(BUGFIX))
    path = tmp_path / "src.json"
    I.write_import_source(imported, path)
    loaded = I.load_import_source(path)
    assert loaded.to_dict() == imported.to_dict()


# -- conversion / scoring ---------------------------------------------------


def test_trust_mode_scores_declared_evidence() -> None:
    task = _load(BUGFIX)
    imported = I.synthesize_import(task)
    outcome = I.import_to_run(imported, task, mode="trust")
    assert outcome.verified is False
    assert outcome.result.outcome == R.RunOutcome.PASSED
    assert outcome.result.agent == imported.agent_label
    # trust mode does not touch a workspace
    assert outcome.result.workspace is None


@pytest.mark.skipif(not HAS_GIT, reason="verify mode's captured diff needs git")
def test_verify_mode_reruns_tests() -> None:
    task = _load(BUGFIX)
    imported = I.synthesize_import(task)
    outcome = I.import_to_run(imported, task, mode="verify", clock=FakeClock(), trace_id="t")
    assert outcome.verified is True
    assert outcome.result.outcome == R.RunOutcome.PASSED
    assert outcome.result.tests is not None and outcome.result.tests["passed"] is True
    assert outcome.result.diff is not None
    assert outcome.trace.trace_id == "t"


@pytest.mark.skipif(not HAS_GIT, reason="verify mode's captured diff needs git")
def test_verify_catches_a_broken_change(tmp_path: Path) -> None:
    """The crux: verification is a real measurement, not a trusted claim.

    A broken change carrying a (false) declared "tests passed" scores ``passed`` in
    trust mode but ``failed`` in verify mode, because verify actually runs the
    tests.
    """
    import dataclasses

    task = _load(BUGFIX)
    before, after = _before_after_dirs(task, tmp_path, fix="    for i in range(1, n - 1):")
    imported = I.import_before_after(before, after, task_id=task.id)
    # Forge a passing declaration, as an over-trusting source might.
    imported = dataclasses.replace(imported, tests={"passed": True, "exit_code": 0})
    trusted = I.import_to_run(imported, task, mode="trust")
    assert trusted.result.outcome == R.RunOutcome.PASSED  # believed the forged claim
    verified = I.import_to_run(imported, task, mode="verify")
    assert verified.result.outcome == R.RunOutcome.FAILED  # measured the truth


@pytest.mark.skipif(not HAS_GIT, reason="round-trip parity needs git for the native diff")
def test_native_run_round_trips_to_same_verdict() -> None:
    """A native run, exported and re-imported, scores identically (the key invariant)."""
    from code_agent_runtime import agents as A

    task = _load(BUGFIX)
    native = R.run_task(task, A.build_scripted_agent(task))
    imported = I.synthesize_import(task)
    verified = I.import_to_run(imported, task, mode="verify")
    assert verified.result.outcome == native.outcome == R.RunOutcome.PASSED
    assert verified.result.tool_call_count == native.tool_call_count


@pytest.mark.skipif(not HAS_GIT, reason="verify mode's captured diff needs git")
def test_verify_supports_expected_files_and_diff_scope() -> None:
    """Verify mode materialises a workspace, so filesystem/diff scorers work too."""
    for task_id in (EXPECTED_FILES, DIFF_SCOPE):
        task = _load(task_id)
        imported = I.synthesize_import(task)
        outcome = I.import_to_run(imported, task, mode="verify")
        assert outcome.result.outcome == R.RunOutcome.PASSED, task_id


def test_verify_required_but_infeasible_raises() -> None:
    task = _load(BUGFIX)
    # A transcript import carries no after-state -> cannot be verified.
    imported = I.import_transcript([{"tool": "Read", "input": {"path": "summation.py"}}], task_id=task.id)
    with pytest.raises(I.ImportSourceError):
        I.import_to_run(imported, task, mode="verify")


def test_auto_falls_back_to_trust_without_after_state() -> None:
    task = _load(BUGFIX)
    text = I.tree_diff({"summation.py": _BUGGY + "\n"}, {"summation.py": _FIXED + "\n"})["diff"]
    imported = I.import_diff_and_log(
        text,
        [{"command": list(task.test_command), "exit_code": 0, "is_test": True}],
        task_id=task.id,
        test_command=list(task.test_command),
    )
    outcome = I.import_to_run(imported, task, mode="auto")
    assert outcome.verified is False
    assert outcome.result.outcome == R.RunOutcome.PASSED


# -- trace fidelity ---------------------------------------------------------


@pytest.mark.skipif(not HAS_GIT, reason="verify mode's captured diff needs git")
def test_produced_trace_is_schema_valid_and_replays() -> None:
    task = _load(BUGFIX)
    imported = I.synthesize_import(task)
    outcome = I.import_to_run(imported, task, mode="verify", clock=FakeClock(), trace_id="tr")

    # Schema round-trip.
    again = TR.Trace.from_dict(outcome.trace.to_dict())
    assert again.trace_id == "tr"

    # Replays with the existing tooling, agreeing with the result.
    replay = TR.replay_trace(outcome.trace)
    assert replay.outcome == R.RunOutcome.PASSED
    assert replay.failure_point is None
    assert replay.tool_call_count == outcome.result.tool_call_count
    # The trace records the imported provenance via the agent label.
    assert outcome.trace.agent == imported.agent_label
    # Events are well-formed (a known-kind timeline ending in run_finished).
    kinds = [e.kind for e in outcome.trace.events]
    assert kinds[0] == "run_started" and kinds[-1] == "run_finished"
    assert "scored" in kinds


def test_trust_trace_has_no_workspace_event() -> None:
    task = _load(BUGFIX)
    imported = I.synthesize_import(task)
    outcome = I.import_to_run(imported, task, mode="trust", clock=FakeClock(), trace_id="tt")
    kinds = [e.kind for e in outcome.trace.events]
    assert "workspace_prepared" not in kinds  # nothing was materialised
    assert outcome.trace.workspace is None


# -- CLI --------------------------------------------------------------------


def test_cli_synthesize_show_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "src.json"
    assert cli.main(["import", "synthesize", BUGFIX, "--dir", str(TASKS_DIR), "--out", str(source)]) == 0
    assert source.is_file()
    data = json.loads(source.read_text())
    assert data["source_kind"] == "synthetic"

    capsys.readouterr()
    assert cli.main(["import", "show", str(source)]) == 0
    out = capsys.readouterr().out
    assert "synthetic" in out and "verifiable" in out

    trace = tmp_path / "out.trace.json"
    rc = cli.main(["import", "run", str(source), "--dir", str(TASKS_DIR), "--trace", str(trace)])
    assert rc == 0
    assert trace.is_file()
    out = capsys.readouterr().out
    assert "outcome      : passed" in out


def test_cli_before_after(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    task = _load(BUGFIX)
    before, after = _before_after_dirs(task, tmp_path, fix=_FIXED)
    source = tmp_path / "ba.json"
    rc = cli.main(
        ["import", "before-after", str(before), str(after), "--task", task.id, "--out", str(source)]
    )
    assert rc == 0
    loaded = I.load_import_source(source)
    assert loaded.source_kind == "before_after" and loaded.has_after_state


def test_cli_run_verify_failed_returns_one(tmp_path: Path) -> None:
    task = _load(BUGFIX)
    before, after = _before_after_dirs(task, tmp_path, fix="    for i in range(1, n - 1):")
    source = tmp_path / "bad.json"
    cli.main(["import", "before-after", str(before), str(after), "--task", task.id, "--out", str(source)])
    if not HAS_GIT:
        pytest.skip("verify mode's captured diff needs git")
    # A broken change, verified, fails -> exit code 1 (CI-friendly gate).
    rc = cli.main(["import", "run", str(source), "--dir", str(TASKS_DIR), "--mode", "verify"])
    assert rc == 1


def test_cli_run_missing_task_errors(tmp_path: Path) -> None:
    # A transcript import without a task_id and no --task cannot be scored.
    imported = I.import_transcript([{"tool": "Read", "input": {"path": "a.py"}}])
    source = tmp_path / "t.json"
    I.write_import_source(imported, source)
    assert cli.main(["import", "run", str(source), "--dir", str(TASKS_DIR)]) == 1
