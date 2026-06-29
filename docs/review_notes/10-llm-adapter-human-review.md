Human review: Milestone 10 — Optional cost-controlled LLM adapter

TL;DR
Adds a model-backed `llm` agent in a new `agents/llm/` subpackage, behind the
safety machinery a paid run needs: a hard pre-call budget guard (prices each
call's worst case — estimated input + full `max_tokens` output — and refuses
*before* contacting the client if it could exceed `--max-cost-usd`; an unpriced
model is refused, not guessed), a content-hash response cache (memory + optional
disk), transcript redaction (reusing the sandbox secret scanner), and a
`--dry-run` cost preview that makes no call. It is **disabled and offline by
default**: with no `--allow-paid`, a deterministic `FakeLLMClient` replays a
task's known-good solution through the model wire format, so the whole path runs
with no API key and no spend; the real `ClaudeAPIClient` lazily imports
`anthropic`. Covered by `tests/test_llm_adapter.py` (34 cases, all offline); the
full suite passes (no paid call, no key, no network).

What changed
- Added `src/code_agent_runtime/agents/llm/` (client, pricing, budget, cache,
  protocol, agent, claude_client, `__init__`).
- `agents/__init__.py`: re-exports the adapter surface.
- `cli.py`: `run --agent llm` + the LLM option group; `_run_llm`,
  `_format_dry_run`; milestone constants bumped to 10/11.
- `pyproject.toml`: optional `claude` extra (`anthropic>=0.40`).
- `scripts/05_llm_adapter_demo.py` (writes gitignored `results/`).
- Tests: `tests/test_llm_adapter.py`; extended `tests/test_scaffold_layout.py`.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`, and the website (index, architecture,
  evals, limitations, roadmap).

What should be checked later
- Pricing accuracy. `agents/llm/pricing.py` hardcodes *approximate* published
  list prices (opus 15/75, sonnet 3/15, haiku 1/5 USD per MTok). Confirm these
  against current Anthropic pricing before any paid run, and that the
  "verify/override; unpriced ⇒ refused" framing is acceptable. `claude-fable-5`
  is intentionally left unpriced.
- Budget-guard semantics. The hard stop is a *pre-call worst-case* bound
  (estimated input via `chars/4` + full `max_tokens` of output). Confirm that is
  the intended guarantee (refuse what *could* exceed, not react to an overrun),
  and that recording provider-reported usage after the call (always ≤ the cleared
  worst case) is the right accounting.
- Offline fake honesty. `build_fake_llm_agent` replays `SOLUTIONS[task.id]` as
  protocol JSON, so an offline `run --agent llm` "passes" because of the scripted
  solution, not model reasoning. Confirm this is clearly enough framed as a
  harness/cost exercise (README, RESULTS, LIMITATIONS, and the demo all say so).
- Redaction placement. The transcript is redacted before storage/sending, but the
  `AgentAction` is parsed from the *raw* reply (so redaction can't break a tool
  call). Confirm that split is what you want, and that redacting what is *sent to*
  the model (not just stored) is acceptable (it can remove info a real model might
  want — deemed correct for secrets).
- Real-client path. `ClaudeAPIClient` is only constructed on `--allow-paid` and
  lazily imports `anthropic`; the mapping is tested via an injected fake SDK
  object. No test hits the network. If you have a key, a manual smoke run
  (`--allow-paid --max-cost-usd 0.25 --dry-run` first, then a real one) is the
  only way to exercise the live API — by design.
- CLI surface. `run --agent llm` gained several flags. Confirm the defaults
  (offline; `claude-haiku-4-5`; memory cache; redaction on; `--allow-paid`
  requires a positive `--max-cost-usd`) match intent.
- Scope. The `llm` agent is deliberately **not** in `DEFAULT_AGENTS`/`eval`, since
  it needs a client+budget the suite does not build. Confirm you want it confined
  to `run` for now.

Technical risks
- Low–moderate. The new code is pure/dependency-free except the optional, lazily
  imported `anthropic`; it never loads at import time (a test asserts `anthropic`
  not in `sys.modules`). The budget guard, cache, redaction, protocol parsing,
  offline solve, dry-run, and CLI are unit-tested offline (34 cases), including a
  refused over-budget call (client never contacted) and disk-cache persistence.
  The main interpretive risk is reading an offline `llm` "pass" as model
  capability — it is the scripted solution; the docs state this. The real-API
  mapping is only fake-SDK-tested, so a live API/SDK change could surface only on
  a real run.

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_llm_adapter.py -q`
- `python3 scripts/05_llm_adapter_demo.py`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm --dry-run --llm-model claude-opus-4-8`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm --allow-paid`  # exits 2: needs budget + key
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
