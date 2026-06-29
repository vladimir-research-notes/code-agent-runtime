"""Tests for the Milestone 10 optional cost-controlled LLM adapter.

CPU-only and offline. **No API key, no network, no ``anthropic`` install** is
required: the model-backed agent is driven entirely by the deterministic
:class:`FakeLLMClient`, and the real Claude client is exercised only through a
dependency-injected fake SDK object. Coverage spans the whole safety surface the
plan names — token/cost estimation, the hard pre-call budget guard, the response
cache, transcript redaction, dry-run preview, the wire protocol, and the CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from code_agent_runtime import agents as A
from code_agent_runtime import cli
from code_agent_runtime import runtime as R
from code_agent_runtime import tasks as TK
from code_agent_runtime.agents.base import Observation
from code_agent_runtime.agents.llm import budget as _budget
from code_agent_runtime.agents.llm import claude_client as _claude
from code_agent_runtime.agents.llm import pricing as _pricing
from code_agent_runtime.agents.llm import protocol as _protocol
from code_agent_runtime.agents.llm.client import (
    FakeLLMClient,
    LLMMessage,
    LLMRequest,
    LLMResponse,
)
from code_agent_runtime.tools import ToolCall

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "tasks"
SOLVABLE = "bugfix/sum-range-off-by-one"
NO_SOLUTION = "security/unsafe-command-demo"


def _load(task_id: str) -> TK.Task:
    return TK.find_task(TASKS_DIR, task_id, resolve_fixture=True)


def _request(model: str = "claude-haiku-4-5", *, content: str = "hello") -> LLMRequest:
    return LLMRequest(model=model, system="sys", messages=(LLMMessage("user", content),))


# --- import hygiene --------------------------------------------------------


def test_importing_package_does_not_require_anthropic() -> None:
    # The whole point of "optional adapter": importing it never pulls a network SDK.
    assert "anthropic" not in sys.modules


# --- pricing ---------------------------------------------------------------


def test_estimate_tokens_bounds() -> None:
    assert _pricing.estimate_tokens("") == 0
    assert _pricing.estimate_tokens(None) == 0
    assert _pricing.estimate_tokens("a") == 1  # non-empty is at least one
    assert _pricing.estimate_tokens("a" * 8) == 2  # ceil(8/4)


def test_lookup_price_exact_prefix_and_unknown() -> None:
    assert _pricing.lookup_price("claude-haiku-4-5") is _pricing.PRICES["claude-haiku-4-5"]
    # A dated alias resolves to its base entry by longest-prefix match.
    assert _pricing.lookup_price("claude-haiku-4-5-20251001") is _pricing.PRICES["claude-haiku-4-5"]
    assert _pricing.lookup_price("totally-unknown-model") is None


def test_cost_usd_math() -> None:
    price = _pricing.ModelPrice(input_usd_per_mtok=3.0, output_usd_per_mtok=15.0)
    # 1M input @ $3 + 1M output @ $15 = $18.
    assert _pricing.cost_usd(price, 1_000_000, 1_000_000) == pytest.approx(18.0)
    assert _pricing.cost_usd(price, 0, 0) == 0.0


# --- request / response data ----------------------------------------------


def test_request_cache_key_is_content_sensitive() -> None:
    a = _request(content="alpha")
    b = _request(content="alpha")
    c = _request(content="beta")
    assert a.cache_key() == b.cache_key()
    assert a.cache_key() != c.cache_key()
    # max_tokens is output-affecting, so it changes the key too.
    d = LLMRequest(model=a.model, system=a.system, messages=a.messages, max_tokens=99)
    assert d.cache_key() != a.cache_key()


def test_response_roundtrip_and_with_cached() -> None:
    resp = LLMResponse(text="hi", model="m", input_tokens=3, output_tokens=1, stop_reason="end_turn")
    assert LLMResponse.from_dict(resp.to_dict()) == resp
    assert resp.with_cached(True).cached is True
    assert resp.with_cached(False) is resp  # no-op returns same object


# --- fake client -----------------------------------------------------------


def test_fake_client_replays_in_order_and_records_requests() -> None:
    client = FakeLLMClient(["one", "two"])
    r1 = client.complete(_request(content="a"))
    r2 = client.complete(_request(content="b"))
    assert (r1.text, r2.text) == ("one", "two")
    assert len(client.requests) == 2
    # Output tokens estimated from the response text; input from the request.
    assert r1.output_tokens == _pricing.estimate_tokens("one")
    assert r1.input_tokens == _request(content="a").estimated_input_tokens()


def test_fake_client_exhaustion_yields_finish() -> None:
    client = FakeLLMClient([])  # no canned responses
    resp = client.complete(_request())
    assert _protocol.parse_action(resp.text).is_finish


def test_fake_client_callable_and_response_passthrough() -> None:
    canned = LLMResponse(text="x", model="other", input_tokens=5, output_tokens=2)
    client = FakeLLMClient([lambda req, i: f"step{i}", canned])
    assert client.complete(_request()).text == "step0"
    pinned = client.complete(_request(model="claude-haiku-4-5"))
    # A passed-through LLMResponse is re-pinned to the request's model.
    assert pinned.model == "claude-haiku-4-5" and pinned.output_tokens == 2


# --- budget guard ----------------------------------------------------------


def test_budget_price_for_override_table_and_unpriced() -> None:
    table_guard = _budget.BudgetGuard(max_cost_usd=1.0)
    assert table_guard.price_for("claude-haiku-4-5") == _pricing.PRICES["claude-haiku-4-5"]
    with pytest.raises(_budget.BudgetUnpriced):
        table_guard.price_for("mystery-model")
    override = _pricing.ModelPrice(1.0, 2.0)
    over_guard = _budget.BudgetGuard(max_cost_usd=1.0, override=override)
    assert over_guard.price_for("mystery-model") is override  # override prices anything


def test_budget_check_refuses_before_call_and_counts_refusal() -> None:
    guard = _budget.BudgetGuard(max_cost_usd=0.0)  # ceiling of $0 → nothing is affordable
    with pytest.raises(_budget.BudgetExceeded):
        guard.check(_request())
    assert guard.refusals == 1
    assert guard.calls == 0  # nothing was ever recorded


def test_budget_check_allows_and_record_tracks_actual() -> None:
    guard = _budget.BudgetGuard(max_cost_usd=1.0)
    worst = guard.check(_request())
    assert worst > 0
    resp = LLMResponse(text="ok", model="claude-haiku-4-5", input_tokens=1000, output_tokens=2000)
    cost = guard.record(resp)
    assert cost == pytest.approx(1000 / 1e6 * 1.0 + 2000 / 1e6 * 5.0)
    assert guard.calls == 1 and guard.spent_usd == pytest.approx(cost)
    assert guard.remaining_usd() == pytest.approx(1.0 - cost)


def test_budget_cached_response_is_free() -> None:
    guard = _budget.BudgetGuard(max_cost_usd=1.0)
    cached = LLMResponse(text="x", model="claude-haiku-4-5", input_tokens=9, output_tokens=9, cached=True)
    assert guard.record(cached) == 0.0
    assert guard.calls == 0 and guard.spent_usd == 0.0


# --- response cache --------------------------------------------------------


def test_cache_memory_hit_miss() -> None:
    cache = A.ResponseCache()
    req = _request()
    assert cache.get(req) is None and cache.misses == 1
    resp = LLMResponse(text="v", model=req.model, input_tokens=1, output_tokens=1)
    cache.put(req, resp)
    hit = cache.get(req)
    assert hit is not None and hit.cached is True and cache.hits == 1


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    req = _request(content="persist-me")
    resp = LLMResponse(text="cached-value", model=req.model, input_tokens=2, output_tokens=2)
    A.ResponseCache(tmp_path).put(req, resp)
    # A fresh cache pointed at the same directory rehydrates from disk.
    again = A.ResponseCache(tmp_path).get(req)
    assert again is not None and again.text == "cached-value" and again.cached is True


# --- wire protocol ---------------------------------------------------------


def test_parse_action_tool_and_finish_variants() -> None:
    tool = _protocol.parse_action('{"tool": "read_file", "args": {"path": "a.py"}}')
    assert tool.kind == "tool" and tool.call.tool == "read_file" and tool.call.args == {"path": "a.py"}
    for blob in (
        '{"action": "finish", "message": "done"}',
        '{"finish": true}',
        '{"done": true}',
    ):
        assert _protocol.parse_action(blob).is_finish


def test_parse_action_tolerates_prose_fences_and_braces() -> None:
    chatty = 'Sure! Here is my action:\n```json\n{"tool": "search_repo", "args": {"query": "a{b}c"}}\n```\nthanks'
    action = _protocol.parse_action(chatty)
    assert action.call.tool == "search_repo" and action.call.args["query"] == "a{b}c"


def test_parse_action_errors() -> None:
    for bad in ("no json here", "{not valid json}", '{"foo": 1}', '{"tool": "x", "args": 5}'):
        with pytest.raises(_protocol.ActionParseError):
            _protocol.parse_action(bad)


def test_action_json_roundtrips_through_parse() -> None:
    call = ToolCall("apply_patch", {"patch": "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n"})
    parsed = _protocol.parse_action(_protocol.action_json(call))
    assert parsed.call.tool == "apply_patch" and parsed.call.args == dict(call.args)
    assert _protocol.parse_action(_protocol.finish_json("bye")).is_finish


def test_system_prompt_lists_tools_and_rules() -> None:
    task = _load(SOLVABLE)
    from code_agent_runtime.tools import build_registry

    specs = build_registry().specs()
    prompt = _protocol.build_system_prompt(task, specs)
    assert "read_file" in prompt and "EXACTLY ONE JSON" in prompt
    assert task.prompt in _protocol.render_task_message(task, specs)


# --- offline LLM agent end to end ------------------------------------------


def test_fake_llm_agent_solves_task_offline() -> None:
    task = _load(SOLVABLE)
    agent = A.build_fake_llm_agent(task)
    result = R.run_task(task, agent)
    assert result.outcome == R.RunOutcome.PASSED
    assert result.agent == "llm" and result.tool_call_count == 3
    usage = agent.usage()
    assert usage["requires_network"] is False
    assert usage["budget"]["calls"] >= 4  # 3 tool actions + 1 finish
    assert usage["budget"]["spent_usd"] > 0  # priced even though offline/free


def test_fake_llm_agent_unknown_task_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        A.build_fake_llm_agent(_load(NO_SOLUTION))


def test_llm_agent_caches_identical_run(tmp_path: Path) -> None:
    task = _load(SOLVABLE)
    cache = A.ResponseCache(tmp_path)
    first = A.build_fake_llm_agent(task, cache=cache)
    R.run_task(task, first)
    assert cache.misses > 0 and cache.hits == 0
    # A second identical run is served entirely from the cache: no new spend.
    second = A.build_fake_llm_agent(task, cache=cache)
    R.run_task(task, second)
    assert cache.hits > 0
    assert second.usage()["budget"]["spent_usd"] == 0.0  # every call was a free cache hit
    assert second.usage()["budget"]["calls"] == 0


def test_llm_agent_budget_exceeded_blocks_call() -> None:
    task = _load(SOLVABLE)
    client = FakeLLMClient(['{"action": "finish", "message": "noop"}'])
    guard = _budget.BudgetGuard(max_cost_usd=0.0)  # nothing affordable
    agent = A.build_llm_agent(task, client, budget=guard)
    agent.reset(task)
    with pytest.raises(_budget.BudgetExceeded):
        agent.propose(Observation(task=task, step=0))
    assert client.requests == []  # the client was never contacted


def test_llm_agent_redacts_secret_from_transcript() -> None:
    task = _load(SOLVABLE)
    secret = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS-key-shaped; built split so the repo stays clean
    client = FakeLLMClient([f'{{"action": "finish", "message": "{secret} all done"}}'])
    agent = A.build_llm_agent(task, client, budget=_budget.BudgetGuard(max_cost_usd=1.0))
    agent.reset(task)
    action = agent.propose(Observation(task=task, step=0))
    assert action.is_finish  # parsed from the RAW reply, so the action still works
    stored = [m["content"] for m in agent.transcript() if m["role"] == "assistant"][0]
    assert secret not in stored and "[redacted" in stored
    assert agent.usage()["transcript_redactions"] >= 1


def test_llm_agent_no_redaction_when_disabled() -> None:
    task = _load(SOLVABLE)
    secret = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS-key-shaped; built split so the repo stays clean
    client = FakeLLMClient([f'{{"action": "finish", "message": "{secret}"}}'])
    agent = A.build_llm_agent(
        task, client, budget=_budget.BudgetGuard(max_cost_usd=1.0), redact_transcript=False
    )
    agent.reset(task)
    agent.propose(Observation(task=task, step=0))
    stored = [m["content"] for m in agent.transcript() if m["role"] == "assistant"][0]
    assert secret in stored  # opted out → raw text kept


# --- dry run ---------------------------------------------------------------


def test_dry_run_plan_prices_without_spending() -> None:
    task = _load(SOLVABLE)
    budget = _budget.BudgetGuard(max_cost_usd=1.0)
    plan = A.dry_run_plan(task, budget=budget)
    assert plan["priced"] is True and plan["worst_case_first_call_usd"] > 0
    assert plan["system_prompt"] and plan["first_user_message"]
    assert budget.spent_usd == 0.0 and budget.calls == 0  # a preview spends nothing


def test_dry_run_plan_unpriced_model_is_not_an_error() -> None:
    task = _load(SOLVABLE)
    cfg = A.LLMAgentConfig(model="brand-new-unpriced-model")
    plan = A.dry_run_plan(task, config=cfg, budget=_budget.BudgetGuard(max_cost_usd=1.0))
    assert plan["priced"] is False and plan["worst_case_first_call_usd"] is None


# --- optional real client (no network, injected fake SDK) ------------------


def test_build_claude_client_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_claude.API_KEY_ENV, raising=False)
    with pytest.raises(A.LLMClientError):
        A.build_claude_client("claude-haiku-4-5")


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    input_tokens = 11
    output_tokens = 7


class _FakeMessage:
    content = [_FakeBlock("hello "), _FakeBlock("world")]
    usage = _FakeUsage()
    model = "claude-haiku-4-5"
    stop_reason = "end_turn"


class _FakeSDK:
    """Stand-in for ``anthropic.Anthropic`` — records the call, returns a message."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):  # noqa: D401 - mimics messages.create
        self.calls.append(kwargs)
        return _FakeMessage()


def test_claude_client_maps_request_and_response() -> None:
    sdk = _FakeSDK()
    client = A.build_claude_client("claude-haiku-4-5", sdk_client=sdk)
    resp = client.complete(_request(content="hi"))
    assert resp.text == "hello world"
    assert (resp.input_tokens, resp.output_tokens) == (11, 7)
    assert sdk.calls[0]["model"] == "claude-haiku-4-5"  # request mapped through


# --- CLI -------------------------------------------------------------------


def test_cli_run_llm_offline_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", SOLVABLE, "--dir", str(TASKS_DIR), "--agent", "llm"])
    assert rc == 0
    out = capsys.readouterr()
    assert "outcome      : passed" in out.out
    assert "llm usage:" in out.err


def test_cli_run_llm_dry_run_makes_no_call(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", SOLVABLE, "--dir", str(TASKS_DIR), "--agent", "llm", "--dry-run"])
    assert rc == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_cli_run_llm_allow_paid_requires_budget(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", SOLVABLE, "--dir", str(TASKS_DIR), "--agent", "llm", "--allow-paid"])
    assert rc == 2
    assert "requires a positive --max-cost-usd" in capsys.readouterr().err


def test_cli_run_llm_no_solution_task_fails_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["run", NO_SOLUTION, "--dir", str(TASKS_DIR), "--agent", "llm"])
    assert rc == 1
    assert "no built-in fake LLM solution" in capsys.readouterr().err
