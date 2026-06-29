"""Tests for the Milestone 7 permission policies and sandbox controls.

CPU-only and offline. The milestone's validation criteria — *blocked actions are
blocked, allowed actions still work* — are exercised at three levels:

- **unit**: the policy (defaults, ``from_task``, serialisation), the path/command
  matchers, and the secret scanner;
- **gating**: ``Sandbox.check_call`` decisions for every rule, and
  ``dispatch_agent_call`` with a sandbox (a denied call is not executed and
  leaves the filesystem untouched; an allowed call's output is redacted);
- **integration**: the built-in unsafe **probe** agent run end to end over
  ``security/unsafe-command-demo`` — every host-escaping action is blocked with
  the expected rule while the benign in-workspace read succeeds.

No destructive command is ever executed: the probe is only run with the sandbox
**on**, so its ``rm``/``curl`` steps are blocked before dispatch. Tests that need
``git`` skip when it is absent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from code_agent_runtime import agents as A
from code_agent_runtime import cli
from code_agent_runtime import runtime as R
from code_agent_runtime import tasks as TK
from code_agent_runtime.sandbox import (
    DEFAULT_COMMAND_DENYLIST,
    NETWORK_PROGRAMS,
    PolicyDecision,
    Sandbox,
    SandboxPolicy,
    count_secrets,
    redact_text,
)
from code_agent_runtime.sandbox.permissions import _path_matches
from code_agent_runtime.tools import ToolCall, ToolContext, ToolResult, build_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
UNSAFE = "security/unsafe-command-demo"
HAS_GIT = shutil.which("git") is not None

# These look like credentials at *runtime* (so redaction has something to find)
# but are assembled from parts in source so the repo hygiene scanner — which
# flags credential-shaped literals — stays clean on this test file.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
_CRED_VALUE = "s3cr3tValue0123456789"


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


def _ctx(path: Path) -> ToolContext:
    return ToolContext.for_dir(path)


def _decide(policy: SandboxPolicy, ctx: ToolContext, tool: str, **args) -> PolicyDecision:
    return Sandbox(policy).check_call(ToolCall(tool, args), ctx)


# --- policy ----------------------------------------------------------------


def test_policy_defaults_are_safe_but_permissive() -> None:
    p = SandboxPolicy()
    assert p.network is False
    assert p.redact_secrets is True
    assert p.allowed_read_paths is None and p.allowed_write_paths is None
    # Ordinary build/test programs are not on the denylist; destructive ones are.
    assert "python3" not in p.command_denylist and "pytest" not in p.command_denylist
    assert "rm" in p.command_denylist and "sudo" in p.command_denylist
    assert ".env" in p.denied_paths and ".git" in p.denied_paths


def test_policy_from_task_reads_resource_limits() -> None:
    # The unsafe demo declares network:false and a 65536-byte output cap.
    p = SandboxPolicy.from_task(_load(UNSAFE))
    assert p.network is False
    assert p.max_output_bytes == 65536


def test_policy_from_task_uses_cpu_seconds_as_runtime_bound() -> None:
    task = TK.validate_task_dict(
        {
            "version": 1,
            "id": "tmp/limits",
            "title": "t",
            "prompt": "p",
            "fixture": "examples/tiny_python_bug",
            "scoring_method": "none",
            "resource_limits": {"cpu_seconds": 7, "network": True},
        }
    )
    p = SandboxPolicy.from_task(task)
    assert p.max_runtime_seconds == 7 and p.network is True


def test_policy_to_dict_is_json_serialisable_and_lists() -> None:
    payload = json.loads(json.dumps(SandboxPolicy().to_dict()))
    assert isinstance(payload["denied_paths"], list)
    assert payload["allowed_read_paths"] is None
    assert payload["network"] is False


# --- path matching ---------------------------------------------------------


@pytest.mark.parametrize(
    "relpath,pattern,expected",
    [
        (".env", ".env", True),
        (".env.local", ".env.*", True),
        (".aws/credentials", ".aws", True),  # directory segment
        ("sub/.git/config", ".git", True),
        ("keys/server.pem", "*.pem", True),  # basename glob
        ("src/main.py", "*.pem", False),
        ("notes.txt", ".env", False),
        ("allowed.txt", "allowed.txt", True),
    ],
)
def test_path_matches(relpath: str, pattern: str, expected: bool) -> None:
    assert _path_matches(relpath, pattern) is expected


# --- check_call: paths -----------------------------------------------------


def test_benign_workspace_read_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    d = _decide(SandboxPolicy(), _ctx(tmp_path), "read_file", path="app.py")
    assert d.allowed and d.rule == "ok"


def test_denied_path_blocks_dotenv_and_credentials(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    for path in (".env", ".aws/credentials", "server.pem"):
        d = _decide(SandboxPolicy(), ctx, "read_file", path=path)
        assert not d.allowed and d.rule == "denied_path", path


def test_outside_workspace_read_and_write_are_blocked(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    ctx = _ctx(ws)
    read = _decide(SandboxPolicy(), ctx, "read_file", path="/etc/shadow")
    assert not read.allowed and read.rule == "outside_workspace"
    write = _decide(SandboxPolicy(), ctx, "write_file", path="../escape.txt", content="x")
    assert not write.allowed and write.rule == "outside_workspace"


def test_allowed_read_paths_restricts_reads(tmp_path: Path) -> None:
    (tmp_path / "allowed.txt").write_text("a", encoding="utf-8")
    (tmp_path / "other.txt").write_text("b", encoding="utf-8")
    policy = SandboxPolicy(allowed_read_paths=["allowed.txt"])
    ctx = _ctx(tmp_path)
    assert _decide(policy, ctx, "read_file", path="allowed.txt").allowed
    blocked = _decide(policy, ctx, "read_file", path="other.txt")
    assert not blocked.allowed and blocked.rule == "read_path_not_allowed"


def test_allowed_write_paths_restricts_writes(tmp_path: Path) -> None:
    policy = SandboxPolicy(allowed_write_paths=["out/*.txt"])
    ctx = _ctx(tmp_path)
    assert _decide(policy, ctx, "write_file", path="out/result.txt", content="x").allowed
    blocked = _decide(policy, ctx, "write_file", path="top.txt", content="x")
    assert not blocked.allowed and blocked.rule == "write_path_not_allowed"


def test_apply_patch_targets_are_path_checked(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    patch = "--- a/.env\n+++ b/.env\n@@ -0,0 +1 @@\n+SECRET=1\n"
    d = _decide(SandboxPolicy(), ctx, "apply_patch", patch=patch)
    assert not d.allowed and d.rule == "denied_path"
    # A patch to an ordinary file is permitted.
    ok_patch = "--- a/mod.py\n+++ b/mod.py\n@@ -0,0 +1 @@\n+x = 1\n"
    assert _decide(SandboxPolicy(), ctx, "apply_patch", patch=ok_patch).allowed


def test_search_and_git_diff_are_not_path_gated(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert _decide(SandboxPolicy(), ctx, "search_repo", query="x").allowed
    assert _decide(SandboxPolicy(), ctx, "git_diff").allowed


def test_missing_or_mistyped_arg_defers_to_the_tool(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    # No path / wrong type → policy can't extract it, so it allows and the tool's
    # own argument validation produces the error.
    assert _decide(SandboxPolicy(), ctx, "read_file").allowed
    assert _decide(SandboxPolicy(), ctx, "read_file", path=123).allowed


# --- check_call: commands + network ----------------------------------------


def test_denylisted_command_is_blocked(tmp_path: Path) -> None:
    d = _decide(SandboxPolicy(), _ctx(tmp_path), "run_shell", command=["rm", "-rf", "."])
    assert not d.allowed and d.rule == "command_denylist" and d.detail["program"] == "rm"


def test_denylist_matches_basename_of_absolute_path(tmp_path: Path) -> None:
    d = _decide(SandboxPolicy(), _ctx(tmp_path), "run_shell", command=["/bin/rm", "x"])
    assert not d.allowed and d.rule == "command_denylist"


def test_network_command_blocked_when_network_off_allowed_when_on(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    off = _decide(SandboxPolicy(), ctx, "run_shell", command="curl http://example.com")
    assert not off.allowed and off.rule == "network_denied"
    on = _decide(SandboxPolicy(network=True), ctx, "run_shell", command="curl http://example.com")
    assert on.allowed
    # Sanity: the program we tested is actually classified as network egress.
    assert "curl" in NETWORK_PROGRAMS


def test_ordinary_command_is_allowed(tmp_path: Path) -> None:
    d = _decide(SandboxPolicy(), _ctx(tmp_path), "run_shell", command=["python3", "-c", "pass"])
    assert d.allowed
    # run_tests with no explicit command uses its safe pytest default.
    assert _decide(SandboxPolicy(), _ctx(tmp_path), "run_tests").allowed


def test_command_allowlist_blocks_everything_else(tmp_path: Path) -> None:
    policy = SandboxPolicy(command_allowlist=["python3"])
    ctx = _ctx(tmp_path)
    assert _decide(policy, ctx, "run_shell", command=["python3", "-V"]).allowed
    blocked = _decide(policy, ctx, "run_shell", command=["bash", "-c", "echo hi"])
    assert not blocked.allowed and blocked.rule == "command_not_allowlisted"


def test_default_denylist_excludes_build_tools() -> None:
    for tool in ("python3", "pytest", "node", "git", "make"):
        assert tool not in DEFAULT_COMMAND_DENYLIST


# --- secret scanner --------------------------------------------------------


def test_redact_text_redacts_credentials_and_keeps_placeholders() -> None:
    cleaned, n = redact_text(f"export AWS_KEY={AWS_KEY}")
    assert n == 1 and AWS_KEY not in cleaned and "redacted" in cleaned

    cred_line = "api" + "_key = " + _CRED_VALUE  # assembled, see note at top
    cleaned2, n2 = redact_text(cred_line)
    assert n2 == 1 and _CRED_VALUE not in cleaned2
    assert cleaned2.startswith("api_key = ")  # key kept, value redacted

    # Paths / placeholders are not treated as secrets.
    assert count_secrets("path = some/dir/looks/long/enough") == 0
    assert count_secrets("password = changeme") == 0


def test_redact_text_passthrough_for_empty_and_none() -> None:
    assert redact_text("") == ("", 0)
    assert redact_text(None) == (None, 0)
    assert count_secrets("nothing secret here") == 0


def test_sandbox_redacts_result_output() -> None:
    sb = Sandbox(SandboxPolicy())
    result = ToolResult(
        tool="run_shell",
        category="exec",
        ok=True,
        summary="ran",
        data={"stdout": f"key found: {AWS_KEY}", "exit_code": 0},
    )
    redacted = sb.redact_result(result)
    assert AWS_KEY not in redacted.data["stdout"]
    assert redacted.data["redacted_secret_count"] == 1
    assert redacted.data["exit_code"] == 0  # non-text fields untouched


def test_redaction_is_noop_when_clean_or_disabled() -> None:
    clean = ToolResult(tool="read_file", category="read", ok=True, summary="ok",
                       data={"content": "no secrets here"})
    # Nothing matched → the same object is returned unchanged.
    assert Sandbox(SandboxPolicy()).redact_result(clean) is clean
    # Redaction off → returned unchanged even with a credential present.
    dirty = ToolResult(tool="run_shell", category="exec", ok=True, summary="s",
                       data={"stdout": AWS_KEY})
    assert Sandbox(SandboxPolicy(redact_secrets=False)).redact_result(dirty) is dirty


# --- dispatch_agent_call with a sandbox ------------------------------------


def test_dispatch_blocks_denied_path_and_does_not_run(tmp_path: Path) -> None:
    from code_agent_runtime.runtime import execution

    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    reg = build_registry()
    sb = Sandbox(SandboxPolicy())
    result, allowed = execution.dispatch_agent_call(
        reg, {"read_file"}, ToolCall("read_file", {"path": ".env"}), _ctx(tmp_path), sandbox=sb
    )
    assert allowed is False
    assert result.category == "blocked" and result.data["policy_rule"] == "denied_path"
    # The tool never ran, so the .env contents are not in the result.
    assert "content" not in result.data


def test_dispatch_redacts_allowed_read(tmp_path: Path) -> None:
    from code_agent_runtime.runtime import execution

    (tmp_path / "conf.txt").write_text(f"token = {AWS_KEY}\n", encoding="utf-8")
    reg = build_registry()
    sb = Sandbox(SandboxPolicy())
    result, allowed = execution.dispatch_agent_call(
        reg, {"read_file"}, ToolCall("read_file", {"path": "conf.txt"}), _ctx(tmp_path), sandbox=sb
    )
    assert allowed is True and result.ok
    assert AWS_KEY not in result.data["content"]
    assert result.data["redacted_secret_count"] == 1


# --- the unsafe probe agent ------------------------------------------------


def test_has_probe_only_for_the_demo() -> None:
    assert A.has_probe(UNSAFE)
    assert not A.has_probe("bugfix/sum-range-off-by-one")


def test_build_probe_for_unknown_task_raises() -> None:
    with pytest.raises(KeyError):
        A.build_unsafe_probe_agent(_load("bugfix/sum-range-off-by-one"))


def test_probe_run_blocks_every_unsafe_action_and_allows_the_benign_read() -> None:
    """The Milestone 7 acceptance run: the sandbox blocks each host-escaping
    action while the benign in-workspace read still works."""
    task = _load(UNSAFE)
    result = R.run_task(task, A.build_unsafe_probe_agent(task))

    assert result.outcome == R.RunOutcome.NOT_SCORED
    assert result.error is None
    # The effective policy is recorded for reproducibility.
    assert result.policy is not None and result.policy["network"] is False

    tool_steps = [s for s in result.steps if s.action_kind == "tool"]
    # Step 0 is the benign read of app.py; the rest are blocked.
    benign = tool_steps[0]
    assert benign.tool == "read_file" and benign.allowed and benign.result.ok

    expected_rules = {
        1: "denied_path",        # read .env
        2: "denied_path",        # read .aws/credentials
        3: "outside_workspace",  # read /etc/shadow
        4: "outside_workspace",  # write ../escape.txt
        5: "outside_workspace",  # write /tmp/car-evil.txt
        6: "command_denylist",   # rm -rf .
        7: "network_denied",     # curl ...
    }
    for index, rule in expected_rules.items():
        step = tool_steps[index]
        assert not step.allowed, (index, step.tool)
        assert step.result.category == "blocked"
        assert step.result.data["policy_rule"] == rule, (index, step.result.data)

    # No exec-category command ran (all were blocked before dispatch).
    assert result.command_count == 0
    # Nothing escaped the workspace.
    assert not (Path(result.workspace).parent / "escape.txt").exists()


def test_probe_blocked_calls_are_visible_in_replay() -> None:
    from code_agent_runtime import traces as TR

    task = _load(UNSAFE)
    _, trace = TR.record_run(task, A.build_unsafe_probe_agent(task))
    run = TR.replay_trace(trace)
    # Seven of the eight probe steps are blocked tool calls.
    assert run.blocked_count == 7
    rules = {tc.tool for tc in run.tool_calls if tc.blocked}
    assert {"read_file", "write_file", "run_shell"} <= rules


# --- enforcement toggle -----------------------------------------------------


def test_disabling_sandbox_drops_policy_and_keeps_runs_working() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task), config=R.RunConfig(enforce_sandbox=False))
    assert result.outcome == R.RunOutcome.PASSED
    assert result.policy is None  # no policy echoed when enforcement is off


def test_enforced_run_records_policy_for_bugfix() -> None:
    task = _load("bugfix/sum-range-off-by-one")
    result = R.run_task(task, A.build_scripted_agent(task))  # default: enforced
    assert result.outcome == R.RunOutcome.PASSED  # permissive defaults don't block the fix
    assert result.policy is not None
    assert json.dumps(result.to_dict())  # policy keeps the result JSON-serialisable


# --- CLI -------------------------------------------------------------------


def test_cli_probe_run_reports_blocks(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", UNSAFE, "--agent", "probe", "--dir", str(TASKS_DIR)])
    out = capsys.readouterr().out
    assert rc == 0  # scoring_method none → not a failure
    assert "BLOCKED" in out and "sandbox" in out


def test_cli_probe_unsupported_task_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", "bugfix/sum-range-off-by-one", "--agent", "probe", "--dir", str(TASKS_DIR)])
    assert rc == 1 and "no built-in sandbox probe" in capsys.readouterr().err


def test_cli_no_sandbox_flag_runs(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(
        ["run", "bugfix/sum-range-off-by-one", "--dir", str(TASKS_DIR), "--no-sandbox", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["outcome"] == "passed" and payload["policy"] is None
