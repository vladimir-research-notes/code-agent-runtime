"""Token estimation and model pricing for the cost guard (Milestone 10).

The optional LLM adapter is only safe to run for real if the runtime can put a
hard ceiling on spend *before* it makes a paid call. That requires two things:
an estimate of how many tokens a request will consume, and a price per token.
Both live here, deliberately separate from any network code, so the budget guard
(:mod:`.budget`) can reason about cost without importing a client and the whole
module stays unit-testable offline.

Two honesty rules shape this file:

- **Token counts are heuristic, never authoritative.** We approximate tokens as
  ``ceil(chars / 4)``. That is good enough to *bound* a call's worst case (which
  is what the guard needs) but it is not a real tokenizer; the authoritative
  count is whatever the provider's API returns, which the guard records *after*
  the call via :func:`cost_usd` on the real usage.
- **An unpriced model cannot be cost-guarded, so it is refused.** :data:`PRICES`
  holds *approximate published list prices* for the Claude models the adapter
  knows about as of the 2026-01 knowledge cutoff. They MUST be verified against
  current Anthropic pricing before any paid run, and they are overridable. A
  model that is not in the table (and has no explicit override) has no price, so
  the guard raises rather than guessing — see :class:`~.budget.BudgetUnpriced`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Rough characters-per-token ratio used only to *estimate* token counts for the
#: pre-call worst-case bound. Not a tokenizer; intentionally conservative-ish.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ModelPrice:
    """Price of a model in US dollars per *million* tokens (input / output)."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float

    def to_dict(self) -> dict[str, float]:
        return {
            "input_usd_per_mtok": self.input_usd_per_mtok,
            "output_usd_per_mtok": self.output_usd_per_mtok,
        }


#: Approximate published list prices (USD per million tokens). **Verify against
#: current Anthropic pricing before a paid run** and override per-run if needed.
#: Models absent here are intentionally left unpriced so the budget guard refuses
#: them rather than guessing a price (e.g. ``claude-fable-5`` is omitted because a
#: reliable rate is not encoded here — supply one explicitly via an override).
PRICES: dict[str, ModelPrice] = {
    "claude-opus-4-8": ModelPrice(15.0, 75.0),
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "claude-haiku-4-5": ModelPrice(1.0, 5.0),
}

#: Cheapest priced model in the table; the adapter's default so a careless real
#: run is as cheap as possible until the operator deliberately picks a bigger one.
DEFAULT_MODEL = "claude-haiku-4-5"


def estimate_tokens(text: str | None) -> int:
    """Estimate the token count of ``text`` as ``ceil(len / CHARS_PER_TOKEN)``.

    Empty/``None`` text is zero tokens; any non-empty text is at least one. This
    is a deliberately crude bound used for cost *estimation*, not a tokenizer.
    """
    if not text:
        return 0
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


def lookup_price(
    model: str,
    prices: dict[str, ModelPrice] | None = None,
) -> ModelPrice | None:
    """Return the :class:`ModelPrice` for ``model``, or ``None`` if unpriced.

    Matches an exact id first, then falls back to the longest known id that is a
    prefix of ``model`` (so a dated alias such as ``claude-haiku-4-5-20251001``
    resolves to the ``claude-haiku-4-5`` entry). Returning ``None`` — rather than
    raising — keeps this a pure lookup; the budget guard decides what an unpriced
    model means (it refuses to run one without an explicit override).
    """
    table = PRICES if prices is None else prices
    if model in table:
        return table[model]
    prefix_matches = [name for name in table if model.startswith(name)]
    if prefix_matches:
        best = max(prefix_matches, key=len)
        return table[best]
    return None


def cost_usd(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    """Dollar cost of ``input_tokens``/``output_tokens`` at ``price``."""
    return (
        input_tokens / 1_000_000 * price.input_usd_per_mtok
        + output_tokens / 1_000_000 * price.output_usd_per_mtok
    )
