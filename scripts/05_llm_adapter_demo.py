#!/usr/bin/env python3
"""Demonstrate the optional cost-controlled LLM adapter (Milestone 10).

A *reproducible, offline, no-spend* tour of the Milestone 10 safety machinery. It
makes **zero** API calls and needs **no** API key: the model-backed
:class:`LLMAgent` is driven by the deterministic :class:`FakeLLMClient`, which
replays a task's known-good solution through the same prompt → parse → action
path a real model would take. It shows, on real runs:

1. **Offline solve.** The LLM agent takes a solvable task from failing tests to
   passing, with the budget guard pricing every (free) call.
2. **Caching.** Re-running with a shared cache serves every call from disk, so
   the second run spends nothing.
3. **Dry-run cost preview.** The estimated worst-case cost of the first call for
   a cheap vs. an expensive model — computed without any call.
4. **Transcript redaction.** A credential-shaped string in a model reply is
   scrubbed from the stored transcript.
5. **Hard budget stop.** A `$0` ceiling makes the guard refuse the call *before*
   the client is ever contacted.

Artifacts are written under ``results/`` (gitignored):

    results/raw/llm_adapter_demo.json
    results/reports/llm_adapter_demo.txt

    python3 scripts/05_llm_adapter_demo.py [--task bugfix/sum-range-off-by-one]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime import agents as _agents  # noqa: E402
from code_agent_runtime import runtime as _runtime  # noqa: E402
from code_agent_runtime import tasks as _tasks  # noqa: E402
from code_agent_runtime.agents.base import Observation  # noqa: E402
from code_agent_runtime.agents.llm import BudgetExceeded, BudgetGuard  # noqa: E402
from code_agent_runtime.agents.llm.client import FakeLLMClient  # noqa: E402

SECRET = "AKIA" + "IOSFODNN7EXAMPLE"  # AWS-key-shaped; built split so the repo stays clean.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", default="bugfix/sum-range-off-by-one", help="Solvable task id.")
    parser.add_argument("--dir", default=str(ROOT / "tasks"), help="Tasks directory.")
    parser.add_argument("--out", default=str(ROOT / "results"), help="Output directory.")
    args = parser.parse_args(argv)

    task = _tasks.find_task(args.dir, args.task, resolve_fixture=True)
    out = Path(args.out)
    summary: dict[str, object] = {"task": task.id, "note": "offline; no API calls; no spend"}

    # 1) Offline solve, with the budget guard pricing every (free) call.
    agent = _agents.build_fake_llm_agent(task)
    result = _runtime.run_task(task, agent)
    summary["solve"] = {"outcome": result.outcome, "usage": agent.usage()}

    # 2) Caching: two runs sharing one cache directory; the 2nd spends nothing.
    cache_dir = out / "cache" / "llm_demo"
    first = _agents.build_fake_llm_agent(task, cache=_agents.ResponseCache(cache_dir))
    _runtime.run_task(task, first)
    shared = _agents.ResponseCache(cache_dir)
    second = _agents.build_fake_llm_agent(task, cache=shared)
    _runtime.run_task(task, second)
    summary["caching"] = {
        "first_spent_usd": first.usage()["budget"]["spent_usd"],
        "second_spent_usd": second.usage()["budget"]["spent_usd"],
        "second_calls": second.usage()["budget"]["calls"],
        "cache": shared.stats(),
    }

    # 3) Dry-run cost preview: cheap vs. expensive model, no call made.
    cheap = _agents.dry_run_plan(task, config=_agents.LLMAgentConfig(model="claude-haiku-4-5"))
    pricey = _agents.dry_run_plan(task, config=_agents.LLMAgentConfig(model="claude-opus-4-8"))
    summary["dry_run"] = {
        "claude-haiku-4-5": cheap["worst_case_first_call_usd"],
        "claude-opus-4-8": pricey["worst_case_first_call_usd"],
        "estimated_input_tokens": cheap["estimated_input_tokens"],
    }

    # 4) Transcript redaction: a secret in a reply is scrubbed before storage.
    redact_client = FakeLLMClient([f'{{"action": "finish", "message": "{SECRET} done"}}'])
    redact_agent = _agents.build_llm_agent(task, redact_client, budget=BudgetGuard(max_cost_usd=1.0))
    redact_agent.reset(task)
    redact_agent.propose(Observation(task=task, step=0))
    stored = [m["content"] for m in redact_agent.transcript() if m["role"] == "assistant"][0]
    summary["redaction"] = {
        "secret_in_transcript": SECRET in stored,
        "redactions": redact_agent.usage()["transcript_redactions"],
    }

    # 5) Hard budget stop: a $0 ceiling refuses the call before contacting it.
    broke = BudgetGuard(max_cost_usd=0.0)
    blocked_client = FakeLLMClient(['{"action": "finish", "message": "noop"}'])
    blocked_agent = _agents.build_llm_agent(task, blocked_client, budget=broke)
    blocked_agent.reset(task)
    try:
        blocked_agent.propose(Observation(task=task, step=0))
        refused = False
    except BudgetExceeded as exc:
        refused = True
        summary["budget_stop"] = {"refused": True, "client_contacted": bool(blocked_client.requests), "reason": str(exc)}
    if not refused:  # pragma: no cover - the guard always refuses a $0 ceiling
        summary["budget_stop"] = {"refused": False}

    # --- persist + print -------------------------------------------------
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "raw" / "llm_adapter_demo.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "Milestone 10 — optional cost-controlled LLM adapter (offline demo)",
        f"  task                 : {task.id}",
        f"  1. offline solve     : {result.outcome} "
        f"(spent ${agent.usage()['budget']['spent_usd']:.6f}, "
        f"{agent.usage()['budget']['calls']} priced calls, network={agent.usage()['requires_network']})",
        f"  2. caching           : 2nd run spent ${second.usage()['budget']['spent_usd']:.6f} "
        f"over {second.usage()['budget']['calls']} calls "
        f"({shared.stats()['hits']} cache hits)",
        f"  3. dry-run 1st call  : haiku ${cheap['worst_case_first_call_usd']:.6f} vs "
        f"opus ${pricey['worst_case_first_call_usd']:.6f} (no call made)",
        f"  4. redaction         : secret in transcript? "
        f"{summary['redaction']['secret_in_transcript']} "
        f"({summary['redaction']['redactions']} redaction(s))",
        f"  5. hard budget stop  : refused before client contacted? "
        f"{summary['budget_stop'].get('refused')} / "
        f"client_contacted={summary['budget_stop'].get('client_contacted')}",
    ]
    report = "\n".join(lines)
    (out / "reports" / "llm_adapter_demo.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nwrote artifacts under {out}/ (gitignored).", file=sys.stderr)

    # Honest non-zero only if an invariant the demo asserts did not hold.
    ok = (
        result.outcome == _runtime.RunOutcome.PASSED
        and second.usage()["budget"]["spent_usd"] == 0.0
        and not summary["redaction"]["secret_in_transcript"]
        and summary["budget_stop"].get("refused") is True
        and summary["budget_stop"].get("client_contacted") is False
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
