"""Tests for the Milestone 3 tool registry and core tools.

CPU-only and offline. Unit tests cover each tool (read/write/search/patch/shell/
tests/git-diff), workspace confinement, and argument validation; an integration
test drives the whole registry over a copy of the ``tiny_python_bug`` fixture —
read, search, patch, and re-run the tests — to prove the tools compose into a
real edit-and-verify loop. Tests that need ``git`` are skipped when it is absent.
"""

from __future__ import annotations

import difflib
import shutil
import subprocess
from pathlib import Path

import pytest

from code_agent_runtime import cli
from code_agent_runtime import tasks as TK
from code_agent_runtime import tools as T

REPO_ROOT = Path(__file__).resolve().parents[1]
HAS_GIT = shutil.which("git") is not None


def _ctx(path: Path, **kw) -> T.ToolContext:
    return T.ToolContext.for_dir(path, **kw)


def _make_patch(path: str, before: str, after: str, *, create: bool = False, delete: bool = False) -> str:
    """Build a unified diff via difflib (realistic hunks, not hand-rolled)."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    fromfile = "/dev/null" if create else f"a/{path}"
    tofile = "/dev/null" if delete else f"b/{path}"
    return "".join(
        difflib.unified_diff(before_lines, after_lines, fromfile=fromfile, tofile=tofile)
    )


def _git_init_commit(ws: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test",
         "commit", "-q", "-m", "init"],
        cwd=ws,
        check=True,
    )


# --- workspace confinement -------------------------------------------------


def test_resolve_within_workspace(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert ctx.resolve("a/b.txt") == (tmp_path / "a" / "b.txt").resolve()
    assert ctx.resolve(".") == tmp_path.resolve()


def test_resolve_rejects_parent_escape(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    with pytest.raises(T.ToolError):
        ctx.resolve("../secret.txt")


def test_resolve_rejects_absolute_outside(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path / "ws")
    (tmp_path / "ws").mkdir()
    with pytest.raises(T.ToolError):
        ctx.resolve("/etc/passwd")


def test_resolve_rejects_symlink_escape(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (ws / "link").symlink_to(outside)
    with pytest.raises(T.ToolError):
        _ctx(ws).resolve("link")


# --- read_file -------------------------------------------------------------


def test_read_file_ok(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    res = T.ReadFileTool().run(_ctx(tmp_path), path="f.txt")
    assert res.ok and res.tool == "read_file" and res.category == "read"
    assert res.data["content"] == "a\nb\nc\n"
    assert res.data["bytes"] == 6 and res.data["lines"] == 3
    assert res.data["binary"] is False and res.data["truncated"] is False


def test_read_missing_file_fails(tmp_path: Path) -> None:
    res = T.ReadFileTool().run(_ctx(tmp_path), path="nope.txt")
    assert not res.ok and "does not exist" in res.error


def test_read_directory_fails(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    res = T.ReadFileTool().run(_ctx(tmp_path), path="d")
    assert not res.ok and "not a regular file" in res.error


def test_read_binary_detected(tmp_path: Path) -> None:
    (tmp_path / "b.bin").write_bytes(b"\x00\x01\x02ABC")
    res = T.ReadFileTool().run(_ctx(tmp_path), path="b.bin")
    assert res.ok and res.data["binary"] is True and res.data["content"] is None


def test_read_truncation(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * 100, encoding="utf-8")
    res = T.ReadFileTool().run(_ctx(tmp_path), path="big.txt", max_bytes=10)
    assert res.ok and res.data["truncated"] is True and len(res.data["content"]) == 10


def test_read_escape_fails(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    res = T.ReadFileTool().run(_ctx(ws), path="../x")
    assert not res.ok and "escapes the workspace" in res.error


# --- write_file ------------------------------------------------------------


def test_write_creates_file(tmp_path: Path) -> None:
    res = T.WriteFileTool().run(_ctx(tmp_path), path="out/new.txt", content="hello\n")
    assert res.ok and res.data["created"] is True and res.data["existed_before"] is False
    assert (tmp_path / "out" / "new.txt").read_text(encoding="utf-8") == "hello\n"


def test_write_overwrite(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("old", encoding="utf-8")
    res = T.WriteFileTool().run(_ctx(tmp_path), path="f.txt", content="new")
    assert res.ok and res.data["created"] is False and res.data["existed_before"] is True
    assert res.data["bytes_before"] == 3
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "new"


def test_write_no_overwrite_fails(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("keep", encoding="utf-8")
    res = T.WriteFileTool().run(_ctx(tmp_path), path="f.txt", content="x", overwrite=False)
    assert not res.ok and "overwrite is disabled" in res.error
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "keep"


def test_write_no_parents_fails(tmp_path: Path) -> None:
    res = T.WriteFileTool().run(
        _ctx(tmp_path), path="missing/dir/f.txt", content="x", create_parents=False
    )
    assert not res.ok and "parent directory does not exist" in res.error


def test_write_over_directory_fails(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    res = T.WriteFileTool().run(_ctx(tmp_path), path="d", content="x")
    assert not res.ok and "directory" in res.error


def test_write_escape_fails(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    res = T.WriteFileTool().run(_ctx(ws), path="../evil.txt", content="x")
    assert not res.ok and "escapes the workspace" in res.error
    assert not (tmp_path / "evil.txt").exists()


# --- search_repo -----------------------------------------------------------


def _seed_searchable(ws: Path) -> None:
    (ws / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (ws / "b.txt").write_text("FOO bar\nbaz\n", encoding="utf-8")
    (ws / ".hidden").mkdir()
    (ws / ".hidden" / "c.py").write_text("foo here too\n", encoding="utf-8")


def test_search_substring(tmp_path: Path) -> None:
    _seed_searchable(tmp_path)
    res = T.SearchRepoTool().run(_ctx(tmp_path), query="foo")
    assert res.ok
    paths = {m["path"] for m in res.data["matches"]}
    assert paths == {"a.py"}  # case-sensitive; .hidden dir skipped
    assert res.data["matches"][0]["line"] == 1


def test_search_ignore_case(tmp_path: Path) -> None:
    _seed_searchable(tmp_path)
    res = T.SearchRepoTool().run(_ctx(tmp_path), query="foo", ignore_case=True)
    assert {m["path"] for m in res.data["matches"]} == {"a.py", "b.txt"}


def test_search_regex(tmp_path: Path) -> None:
    _seed_searchable(tmp_path)
    res = T.SearchRepoTool().run(_ctx(tmp_path), query=r"def \w+\(", regex=True)
    assert res.data["match_count"] == 1 and res.data["matches"][0]["path"] == "a.py"


def test_search_glob_filter(tmp_path: Path) -> None:
    _seed_searchable(tmp_path)
    res = T.SearchRepoTool().run(_ctx(tmp_path), query="foo", ignore_case=True, glob="*.txt")
    assert {m["path"] for m in res.data["matches"]} == {"b.txt"}


def test_search_max_results_truncates(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("hit\n" * 10, encoding="utf-8")
    res = T.SearchRepoTool().run(_ctx(tmp_path), query="hit", max_results=3)
    assert res.data["match_count"] == 3 and res.data["truncated"] is True


def test_search_invalid_regex_fails(tmp_path: Path) -> None:
    res = T.SearchRepoTool().run(_ctx(tmp_path), query="(", regex=True)
    assert not res.ok and "invalid regex" in res.error


# --- apply_patch -----------------------------------------------------------


def test_apply_modify(tmp_path: Path) -> None:
    original = "line one\nline two\nline three\n"
    (tmp_path / "f.txt").write_text(original, encoding="utf-8")
    fixed = original.replace("line two", "line 2")
    res = T.ApplyPatchTool().run(_ctx(tmp_path), patch=_make_patch("f.txt", original, fixed))
    assert res.ok and res.data["files_changed"] == 1
    assert res.data["insertions"] == 1 and res.data["deletions"] == 1
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == fixed


def test_apply_create(tmp_path: Path) -> None:
    after = "brand new\nsecond line\n"
    res = T.ApplyPatchTool().run(
        _ctx(tmp_path), patch=_make_patch("new.txt", "", after, create=True)
    )
    assert res.ok and res.data["files"][0]["mode"] == "create"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == after


def test_apply_delete(tmp_path: Path) -> None:
    original = "a\nb\n"
    (tmp_path / "gone.txt").write_text(original, encoding="utf-8")
    res = T.ApplyPatchTool().run(
        _ctx(tmp_path), patch=_make_patch("gone.txt", original, "", delete=True)
    )
    assert res.ok and res.data["files"][0]["mode"] == "delete"
    assert not (tmp_path / "gone.txt").exists()


def test_apply_context_mismatch_fails_and_leaves_file(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    # Patch built against a different base; context will not match.
    bad = _make_patch("f.txt", "x\ny\nz\n", "x\nY\nz\n")
    res = T.ApplyPatchTool().run(_ctx(tmp_path), patch=bad)
    assert not res.ok and "context does not match" in res.error
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "a\nb\nc\n"


def test_apply_is_atomic_across_files(tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("keep\nme\n", encoding="utf-8")
    (tmp_path / "bad.txt").write_text("real\ncontent\n", encoding="utf-8")
    good = _make_patch("ok.txt", "keep\nme\n", "kept\nme\n")
    bad = _make_patch("bad.txt", "wrong\nbase\n", "wrong\nBASE\n")
    res = T.ApplyPatchTool().run(_ctx(tmp_path), patch=good + bad)
    assert not res.ok
    # First file must be untouched because the second hunk failed to apply.
    assert (tmp_path / "ok.txt").read_text(encoding="utf-8") == "keep\nme\n"


def test_apply_empty_patch_fails(tmp_path: Path) -> None:
    res = T.ApplyPatchTool().run(_ctx(tmp_path), patch="not a patch at all\n")
    assert not res.ok and "no file sections" in res.error


def test_apply_create_existing_fails(tmp_path: Path) -> None:
    (tmp_path / "exists.txt").write_text("here\n", encoding="utf-8")
    res = T.ApplyPatchTool().run(
        _ctx(tmp_path), patch=_make_patch("exists.txt", "", "x\n", create=True)
    )
    assert not res.ok and "already exists" in res.error


# --- run_shell -------------------------------------------------------------


def test_run_shell_success(tmp_path: Path) -> None:
    res = T.RunShellTool().run(_ctx(tmp_path), command=["python3", "-c", "print('hi')"])
    assert res.ok and res.data["exit_code"] == 0
    assert res.data["stdout"].strip() == "hi" and res.data["timed_out"] is False


def test_run_shell_nonzero_exit_is_recorded(tmp_path: Path) -> None:
    res = T.RunShellTool().run(_ctx(tmp_path), command=["python3", "-c", "import sys; sys.exit(3)"])
    # The command *ran*, so the tool call succeeds; the exit code lives in data.
    assert res.ok and res.data["exit_code"] == 3


def test_run_shell_string_is_split(tmp_path: Path) -> None:
    res = T.RunShellTool().run(_ctx(tmp_path), command="python3 -c \"print(1 + 1)\"")
    assert res.ok and res.data["stdout"].strip() == "2"


def test_run_shell_command_not_found(tmp_path: Path) -> None:
    res = T.RunShellTool().run(_ctx(tmp_path), command=["definitely-not-a-real-binary-xyz"])
    assert not res.ok and "command not found" in res.error


def test_run_shell_truncates_output(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, max_output_bytes=8)
    res = T.RunShellTool().run(ctx, command=["python3", "-c", "print('x' * 1000)"])
    assert res.ok and res.data["truncated"] is True and len(res.data["stdout"]) == 8


def test_run_shell_timeout(tmp_path: Path) -> None:
    res = T.RunShellTool().run(
        _ctx(tmp_path), command=["python3", "-c", "import time; time.sleep(5)"], timeout_seconds=1
    )
    assert res.ok and res.data["timed_out"] is True


# --- run_tests -------------------------------------------------------------


def test_run_tests_passed_true(tmp_path: Path) -> None:
    res = T.RunTestsTool().run(_ctx(tmp_path), command=["python3", "-c", "pass"])
    assert res.ok and res.data["passed"] is True


def test_run_tests_passed_false(tmp_path: Path) -> None:
    res = T.RunTestsTool().run(_ctx(tmp_path), command=["python3", "-c", "import sys; sys.exit(1)"])
    assert res.ok and res.data["passed"] is False


# --- git_diff --------------------------------------------------------------


def test_git_diff_not_a_repo(tmp_path: Path) -> None:
    res = T.GitDiffTool().run(_ctx(tmp_path))
    assert not res.ok and "not a git repository" in res.error


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_git_diff_reports_changes(tmp_path: Path) -> None:
    (tmp_path / "tracked.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git_init_commit(tmp_path)
    (tmp_path / "tracked.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    res = T.GitDiffTool().run(_ctx(tmp_path))
    assert res.ok and res.data["is_git_repo"] is True
    assert "three" in res.data["diff"]
    assert res.data["insertions"] == 1 and res.data["deletions"] == 0
    assert res.data["files"][0]["path"] == "tracked.txt"
    assert "untracked.txt" in res.data["untracked"]


# --- argument validation (via Tool.run) ------------------------------------


def test_missing_required_arg(tmp_path: Path) -> None:
    res = T.ReadFileTool().run(_ctx(tmp_path))
    assert not res.ok and "missing required argument 'path'" in res.error


def test_unknown_arg_rejected(tmp_path: Path) -> None:
    res = T.ReadFileTool().run(_ctx(tmp_path), path="f", bogus=1)
    assert not res.ok and "unknown argument" in res.error


def test_wrong_type_rejected(tmp_path: Path) -> None:
    res = T.ReadFileTool().run(_ctx(tmp_path), path=123)
    assert not res.ok and "must be str" in res.error


def test_bool_not_accepted_for_int_param(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    res = T.ReadFileTool().run(_ctx(tmp_path), path="f.txt", max_bytes=True)
    assert not res.ok and "must be int" in res.error


# --- registry --------------------------------------------------------------


def test_registry_has_all_tools() -> None:
    reg = T.build_registry()
    assert len(reg) == 7
    assert set(reg.names()) == set(T.REGISTERED_TOOL_NAMES)


def test_registered_names_match_task_known_tools() -> None:
    # The schema's closed vocabulary must equal the live registry, or a task
    # could reference a tool that cannot run. This guards against drift.
    assert T.REGISTERED_TOOL_NAMES == TK.KNOWN_TOOLS


def test_every_spec_has_valid_category() -> None:
    for spec in T.build_registry().specs():
        assert spec.category in T.TOOL_CATEGORIES
        assert spec.summary


def test_dispatch_unknown_tool_is_structured_failure(tmp_path: Path) -> None:
    res = T.build_registry().dispatch(T.ToolCall("nope"), _ctx(tmp_path))
    assert not res.ok and res.category == "unknown" and "unknown tool" in res.error


def test_dispatch_runs_tool(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hello", encoding="utf-8")
    res = T.build_registry().dispatch(T.ToolCall("read_file", {"path": "f.txt"}), _ctx(tmp_path))
    assert res.ok and res.data["content"] == "hello"


def test_subset_selects_and_validates() -> None:
    reg = T.build_registry().subset(["read_file", "write_file"])
    assert set(reg.names()) == {"read_file", "write_file"}
    with pytest.raises(KeyError):
        T.build_registry().subset(["read_file", "no_such_tool"])


def test_result_is_json_serialisable(tmp_path: Path) -> None:
    import json

    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    res = T.ReadFileTool().run(_ctx(tmp_path), path="f.txt")
    assert json.dumps(res.to_dict())  # does not raise


# --- CLI -------------------------------------------------------------------


def test_cli_tools_list(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tools", "list"])
    out = capsys.readouterr().out
    assert rc == 0 and "read_file" in out and "[read" in out


def test_cli_tools_list_json(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    rc = cli.main(["tools", "list", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["count"] == 7
    assert {t["name"] for t in payload["tools"]} == set(T.REGISTERED_TOOL_NAMES)


def test_cli_tools_show(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tools", "show", "apply_patch"])
    out = capsys.readouterr().out
    assert rc == 0 and "Tool: apply_patch" in out and "patch" in out


def test_cli_tools_show_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tools", "show", "no_such_tool"])
    assert rc == 1 and "unknown tool" in capsys.readouterr().err


def test_cli_tools_no_action_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tools"])
    assert rc == 0 and "list" in capsys.readouterr().out


# --- integration over a real fixture repo ----------------------------------


def test_integration_fix_bug_on_fixture(tmp_path: Path) -> None:
    """Drive the registry through a full read → search → patch → test loop."""
    ws = tmp_path / "work"
    shutil.copytree(REPO_ROOT / "examples" / "tiny_python_bug", ws)
    ctx = _ctx(ws)
    reg = T.build_registry()

    # Tests fail against the buggy fixture.
    before = reg.dispatch(
        T.ToolCall("run_tests", {"command": ["python3", "-m", "pytest", "-q"]}), ctx
    )
    assert before.ok and before.data["passed"] is False

    # Read the buggy file and locate the bug.
    read = reg.dispatch(T.ToolCall("read_file", {"path": "summation.py"}), ctx)
    assert read.ok
    original = read.data["content"]
    found = reg.dispatch(T.ToolCall("search_repo", {"query": "range(1, n)"}), ctx)
    assert found.ok and found.data["match_count"] >= 1

    # Patch the off-by-one and confirm the tests now pass.
    fixed = original.replace("range(1, n):", "range(1, n + 1):")
    assert fixed != original
    applied = reg.dispatch(
        T.ToolCall("apply_patch", {"patch": _make_patch("summation.py", original, fixed)}), ctx
    )
    assert applied.ok and applied.data["files_changed"] == 1

    after = reg.dispatch(
        T.ToolCall("run_tests", {"command": ["python3", "-m", "pytest", "-q"]}), ctx
    )
    assert after.ok and after.data["passed"] is True


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_integration_git_diff_after_edit(tmp_path: Path) -> None:
    ws = tmp_path / "work"
    shutil.copytree(REPO_ROOT / "examples" / "tiny_python_bug", ws)
    _git_init_commit(ws)
    ctx = _ctx(ws)
    reg = T.build_registry()

    read = reg.dispatch(T.ToolCall("read_file", {"path": "summation.py"}), ctx)
    fixed = read.data["content"].replace("range(1, n):", "range(1, n + 1):")
    reg.dispatch(T.ToolCall("write_file", {"path": "summation.py", "content": fixed}), ctx)

    diff = reg.dispatch(T.ToolCall("git_diff"), ctx)
    assert diff.ok and diff.data["insertions"] >= 1
    assert any(f["path"] == "summation.py" for f in diff.data["files"])
