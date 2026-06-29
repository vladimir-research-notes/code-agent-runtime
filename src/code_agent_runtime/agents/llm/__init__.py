"""Optional, cost-controlled LLM adapter (Milestone 10).

A model-backed agent that plugs into the runtime's one-action-per-step contract,
wrapped in the safety machinery a paid run requires: a hard pre-call budget guard,
a response cache, transcript redaction, a dry-run preview, and an offline fake
client so the whole path is exercised with no API key and no spend.

The design keeps the real provider strictly optional. Nothing here imports a
network library at module load: the abstract :class:`LLMClient` and the offline
:class:`FakeLLMClient` carry the default path; the real :class:`ClaudeAPIClient`
lazily imports ``anthropic`` only when actually constructed. See ``docs/PLAN.md``
(Milestone 10) and ``docs/METHODOLOGY.md``.

Public API:

- :class:`LLMAgent`, :class:`LLMAgentConfig` — the agent and its knobs.
- :func:`build_llm_agent`, :func:`build_fake_llm_agent`, :func:`dry_run_plan` —
  construction and cost preview.
- :class:`LLMClient`, :class:`FakeLLMClient`, :class:`LLMRequest`,
  :class:`LLMResponse`, :class:`LLMMessage`, :class:`LLMClientError` — the seam.
- :class:`BudgetGuard`, :class:`BudgetError`, :class:`BudgetExceeded`,
  :class:`BudgetUnpriced` — the cost guard.
- :class:`ResponseCache` — the response cache.
- :class:`ModelPrice`, :data:`PRICES`, :data:`DEFAULT_MODEL`,
  :func:`estimate_tokens`, :func:`lookup_price`, :func:`cost_usd` — pricing.
- :class:`ClaudeAPIClient`, :func:`build_claude_client` — the optional real adapter.
- :func:`parse_action`, :class:`ActionParseError` — the wire protocol.
"""

from __future__ import annotations

from .agent import (
    DEFAULT_OFFLINE_BUDGET_USD,
    LLMAgent,
    LLMAgentConfig,
    build_fake_llm_agent,
    build_llm_agent,
    dry_run_plan,
)
from .budget import BudgetError, BudgetExceeded, BudgetGuard, BudgetUnpriced
from .cache import ResponseCache
from .claude_client import API_KEY_ENV, ClaudeAPIClient, build_claude_client
from .client import (
    FakeLLMClient,
    LLMClient,
    LLMClientError,
    LLMMessage,
    LLMRequest,
    LLMResponse,
)
from .pricing import (
    CHARS_PER_TOKEN,
    DEFAULT_MODEL,
    PRICES,
    ModelPrice,
    cost_usd,
    estimate_tokens,
    lookup_price,
)
from .protocol import ActionParseError, action_json, finish_json, parse_action

__all__ = [
    "LLMAgent",
    "LLMAgentConfig",
    "build_llm_agent",
    "build_fake_llm_agent",
    "dry_run_plan",
    "DEFAULT_OFFLINE_BUDGET_USD",
    "LLMClient",
    "FakeLLMClient",
    "LLMClientError",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "BudgetGuard",
    "BudgetError",
    "BudgetExceeded",
    "BudgetUnpriced",
    "ResponseCache",
    "ModelPrice",
    "PRICES",
    "DEFAULT_MODEL",
    "CHARS_PER_TOKEN",
    "estimate_tokens",
    "lookup_price",
    "cost_usd",
    "ClaudeAPIClient",
    "build_claude_client",
    "API_KEY_ENV",
    "parse_action",
    "action_json",
    "finish_json",
    "ActionParseError",
]
