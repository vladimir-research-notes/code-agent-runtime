# Milestone 10 — Optional cost-controlled LLM adapter

## Summary

A model-backed `llm` agent that plugs into the runtime's existing
one-action-per-step contract, wrapped in the safety machinery the plan requires
for a paid run. Everything ships in a new `agents/llm/` subpackage and is
**disabled and offline by default**: the agent is driven by a deterministic
`FakeLLMClient` unless a real run is explicitly opted into, the real
`ClaudeAPIClient` lazily imports `anthropic`, and the agent never appears in the
default eval matrix. No test makes a paid call and no API key is required.

The path on each `propose` step:

1. render the next user turn (the task, or the previous tool result) and append
   it to the transcript **after redaction**, so a credential-shaped string a tool
   surfaced never reaches the model or disk;
2. look the request up in the response cache — a hit is free and skips the rest;
3. on a miss, the budget guard prices the call's **worst case** and refuses
   *before* contacting the client if it could exceed the ceiling; then the call
   is made, actual usage recorded, and the response cached;
4. parse the reply into one `AgentAction`; a malformed reply ends the run cleanly
   instead of crashing the loop.

## Plan requirements → where they live

| Requirement | Implementation |
| --- | --- |
| Abstract LLM-agent interface | `client.LLMClient` (ABC) + `LLMRequest`/`LLMResponse`/`LLMMessage`; `agent.LLMAgent` |
| Optional Claude API adapter | `claude_client.ClaudeAPIClient` / `build_claude_client` — lazy `anthropic` import |
| Disabled by default | not in `DEFAULT_AGENTS`; `run --agent llm` is offline unless `--allow-paid`; real client only built on opt-in |
| No paid calls in tests | tests use `FakeLLMClient` only; the real client is exercised via an injected fake SDK object |
| Fake client for unit tests | `client.FakeLLMClient` (deterministic, offline, heuristic token counts) |
| Explicit `--max-cost-usd` | `budget.BudgetGuard(max_cost_usd=...)`; required (positive) for `--allow-paid` |
| Dry-run mode | `agent.dry_run_plan` + `run --agent llm --dry-run` — prints request + worst-case cost, makes no call |
| Caching | `cache.ResponseCache` (content-hash; memory + optional disk) |
| Transcript redaction | `LLMAgent` runs every stored turn through `sandbox.secret_scanner.redact_text` |
| Hard stop on budget risk | `BudgetGuard.check` prices the worst case **before** the call and raises `BudgetExceeded`; an unpriced model raises `BudgetUnpriced` |

## Deliverables

- `src/code_agent_runtime/agents/llm/`:
  - `pricing.py` — `estimate_tokens` (chars/4 heuristic), `ModelPrice`, the
    approximate `PRICES` table (opus/sonnet/haiku) + `DEFAULT_MODEL`,
    `lookup_price` (exact then longest-prefix), `cost_usd`.
  - `client.py` — `LLMMessage`/`LLMRequest`/`LLMResponse` (JSON round-trip,
    `cache_key`, token estimation), the `LLMClient` ABC, `FakeLLMClient`,
    `LLMClientError`.
  - `budget.py` — `BudgetGuard` (`check`/`record`/`remaining_usd`/`to_dict`),
    `BudgetError`/`BudgetExceeded`/`BudgetUnpriced`.
  - `cache.py` — `ResponseCache` (memory + optional per-key JSON files).
  - `protocol.py` — `build_system_prompt`/`render_task_message`/
    `render_step_message`, `parse_action` (tolerant first-balanced-object
    extraction), `action_json`/`finish_json`, `ActionParseError`.
  - `agent.py` — `LLMAgent`, `LLMAgentConfig`, `build_llm_agent`,
    `build_fake_llm_agent`, `dry_run_plan`, `DEFAULT_OFFLINE_BUDGET_USD`.
  - `claude_client.py` — `ClaudeAPIClient`, `build_claude_client`, `API_KEY_ENV`.
  - `__init__.py` — the subpackage's public surface.
- `agents/__init__.py` — re-exports the adapter's key names.
- `cli.py` — `run --agent llm` with `--llm-model`, `--max-cost-usd`,
  `--max-output-tokens`, `--dry-run`, `--allow-paid`, `--cache-dir`, `--no-cache`,
  `--no-redact-transcript`, `--show-transcript`; `_run_llm` + `_format_dry_run`;
  milestone constants bumped to 10/11.
- `pyproject.toml` — optional `claude` extra (`anthropic>=0.40`).
- `scripts/05_llm_adapter_demo.py` — offline tour: solve, caching, dry-run cost,
  redaction, hard budget stop (writes gitignored `results/` artifacts).
- Tests: `tests/test_llm_adapter.py` (34 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 10 notes.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`; website `index.html`, `architecture.html`,
  `evals.html`, `limitations.html`, `roadmap.html` (and `results.html` via the
  RESULTS narrative).

## Design notes / decisions

- **Optional means optional at import time.** No module in the package imports a
  network library at load. `claude_client` imports `anthropic` lazily inside the
  constructor, *after* the key check, so a missing key or missing package is a
  clean `LLMClientError`, not an import crash. A test asserts `anthropic` is not
  in `sys.modules` after importing the package.
- **Hard stop is a *pre-call* worst-case bound.** The guard refuses a call whose
  worst case (estimated input + full `max_tokens` of output) *could* exceed the
  ceiling — it does not wait to discover an overrun. Actual usage recorded after
  the call is always ≤ the cleared worst case. A cached response is free and not
  recorded.
- **Unpriced ⇒ refused, not guessed.** A model with no table price and no
  override cannot be bounded, so the guard raises rather than inventing a number.
  `claude-fable-5` is deliberately left unpriced; the pricing table is documented
  as *approximate* and must be verified before a paid run.
- **The offline fake replays known-good solutions.** `build_fake_llm_agent`
  reuses `agents.solutions.SOLUTIONS` and formats each `ToolCall` as protocol
  JSON, so the model-backed path solves the example tasks end to end — exercising
  the guard, cache, and redaction — with no spend. This demonstrates the
  *harness*, not model reasoning, and is documented as such.
- **Redaction reuses the one source of truth.** Transcript redaction calls the
  same `secret_scanner.redact_text` the sandbox uses, so the runtime redactor,
  the trace redactor, and the commit-time hygiene scanner never drift apart. The
  action is parsed from the *raw* reply, so redacting the stored copy never breaks
  the tool call.
- **The adapter stays out of the default suite.** `DEFAULT_AGENTS` is unchanged
  (mock/scripted/probe). The `llm` agent is reachable only via `run --agent llm`,
  which needs a client and budget the suite does not construct — keeping the eval
  matrix deterministic and free.

## Honest limitations (carried into docs)

- Pricing is approximate published list pricing baked into a table; **verify
  against current Anthropic pricing before a paid run.** It is overridable.
- Token counts are a `chars/4` heuristic, adequate for bounding the worst case
  but not an exact predictor; provider-reported usage is recorded after the call.
- The offline fake agent replays a fixed solution — a plumbing/cost baseline, not
  a capability measurement.
- Transcript redaction is heuristic (same patterns as the hygiene scanner) and is
  off under `--no-redact-transcript`.
- No real paid run is part of any test or committed result; the real client is
  validated only through an injected fake SDK object.

## Validation

- `python3 -m pytest -q` — full CPU-only suite passes (`tests/test_llm_adapter.py`
  added, 34 cases). No API key, no `anthropic`, no network.
- `python3 scripts/05_llm_adapter_demo.py` — offline solve (passed), caching (2nd
  run $0 over 4 hits), dry-run (haiku ≈ $0.0056 vs opus ≈ $0.083), redaction
  (secret scrubbed), hard budget stop (refused before client contacted). Exit 0.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm`
  — offline solve; `--dry-run` previews cost with no call; `--allow-paid` without a
  key/budget fails cleanly (exit 2).
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 11 — Claude Code trace importer.
