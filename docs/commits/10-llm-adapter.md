# Commit note — Milestone 10

**Commit message:** `Add optional cost-controlled LLM adapter`

## What this commit adds

- `src/code_agent_runtime/agents/llm/` — the optional, cost-guarded LLM adapter:
  - `pricing.py` — `estimate_tokens`, `ModelPrice`, the approximate `PRICES`
    table + `DEFAULT_MODEL`, `lookup_price`, `cost_usd`.
  - `client.py` — `LLMClient` ABC, `FakeLLMClient`, `LLMRequest`/`LLMResponse`/
    `LLMMessage`, `LLMClientError`.
  - `budget.py` — `BudgetGuard` (hard pre-call worst-case stop), `BudgetError`/
    `BudgetExceeded`/`BudgetUnpriced`.
  - `cache.py` — `ResponseCache` (content-hash; memory + optional disk).
  - `protocol.py` — prompt building, `parse_action`, `action_json`/`finish_json`,
    `ActionParseError`.
  - `agent.py` — `LLMAgent`, `LLMAgentConfig`, `build_llm_agent`,
    `build_fake_llm_agent`, `dry_run_plan`.
  - `claude_client.py` — `ClaudeAPIClient` / `build_claude_client` (lazy
    `anthropic`).
- `src/code_agent_runtime/agents/__init__.py` — re-exports the adapter surface.
- `cli.py` — `run --agent llm` and the LLM option group (`--llm-model`,
  `--max-cost-usd`, `--max-output-tokens`, `--dry-run`, `--allow-paid`,
  `--cache-dir`, `--no-cache`, `--no-redact-transcript`, `--show-transcript`);
  `_run_llm` / `_format_dry_run`; milestone constants bumped to 10/11.
- `pyproject.toml` — optional `claude` extra (`anthropic>=0.40`).
- `scripts/05_llm_adapter_demo.py` — offline demo (writes gitignored `results/`).
- Tests: `tests/test_llm_adapter.py` (34 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 10 notes.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`; `index.html`, `architecture.html`,
  `evals.html`, `limitations.html`, `roadmap.html`; Milestone 10 milestone/commit/
  review notes.

## Excluded (per operating principles)

No secrets, API keys, virtualenvs, caches, `node_modules`, weights, or large
artifacts. **No paid API call** anywhere in tests or committed results. The only
new dependency is the *optional* `anthropic` extra, never imported unless a real
run is opted into; the core runtime and the full test suite stay dependency-free
and offline. Generated `results/` artifacts (incl. the demo's response cache)
remain gitignored; the committed narrative in `docs/RESULTS.md` is the canonical
record.

## Honesty notes

The adapter is disabled and offline by default. The default `run --agent llm`
path uses a deterministic `FakeLLMClient` that replays a task's known-good
solution through the model wire format — it demonstrates the harness and the cost
guard, **not** model reasoning. The cost guard is a *pre-call worst-case* hard
stop, and an unpriced model is refused rather than estimated. Pricing is
approximate published list pricing baked into a table that must be verified
against current Anthropic pricing before a paid run (it is overridable); token
counts are a `chars/4` heuristic, not a tokenizer. The real `ClaudeAPIClient` is
validated only through an injected fake SDK object — no network, no key.

## Verification at commit time

- `python3 -m pytest -q` passes (`tests/test_llm_adapter.py` added; 34 cases). No
  API key or `anthropic` install required.
- `python3 scripts/05_llm_adapter_demo.py` prints the offline tour (solve /
  caching / dry-run / redaction / hard budget stop) and exits 0.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one
  --agent llm` solves offline; `--dry-run` previews cost with no call;
  `--allow-paid` without a key/budget fails cleanly.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
