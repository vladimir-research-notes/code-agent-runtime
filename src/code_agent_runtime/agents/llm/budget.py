"""The cost guard: a hard ceiling on LLM spend (Milestone 10).

This is the safety mechanism that makes a real, paid run defensible. The guard
sits between the agent and the client and enforces a single rule:

    Never make a call that *could* push cumulative spend past ``max_cost_usd``.

The emphasis on *could* matters. :meth:`BudgetGuard.check` runs **before** the
call and prices the call's **worst case** — the estimated input tokens plus the
full ``max_tokens`` of output at the model's output rate. If that worst case,
added to what has already been spent, would exceed the budget, the guard raises
:class:`BudgetExceeded` and the call is never made. So the guarantee is a
*pre-call* hard stop, not an after-the-fact "oops, we went over".

After a call succeeds, :meth:`record` adds the **actual** usage the provider
reported, so cumulative spend tracks reality (always ≤ the worst case the guard
already cleared). A cached response is free and is never recorded.

An **unpriced model** cannot be bounded, so the guard refuses it
(:class:`BudgetUnpriced`) unless the operator supplies an explicit price
override. "We don't know what this costs" is treated as a stop condition, not a
reason to proceed. The guard is duck-typed against the request object (it only
needs ``model``, ``max_tokens``, and ``estimated_input_tokens()``), so it has no
import dependency on the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import pricing
from .pricing import ModelPrice

#: Tiny tolerance so floating-point rounding never spuriously trips the ceiling.
_EPSILON = 1e-9


class BudgetError(RuntimeError):
    """Base class for budget-guard refusals."""


class BudgetExceeded(BudgetError):
    """A call's worst-case cost would push spend past the budget — refused."""


class BudgetUnpriced(BudgetError):
    """The model has no known price and no override, so it cannot be guarded."""


@dataclass
class BudgetGuard:
    """Track LLM spend and refuse any call that risks exceeding the ceiling.

    ``max_cost_usd`` is the hard ceiling. ``override`` forces a single
    :class:`ModelPrice` for *every* model (use it for an unpriced model or a
    negotiated rate); otherwise prices come from ``prices`` (default
    :data:`~.pricing.PRICES`). The running totals (:attr:`spent_usd`, token
    counts, :attr:`calls`) are public so a report can show exactly what a run
    cost.
    """

    max_cost_usd: float
    prices: dict[str, ModelPrice] | None = None
    override: ModelPrice | None = None
    spent_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    #: Worst-case cost the guard has *cleared* (sum over checks). Always ≥ spent.
    projected_usd: float = 0.0
    refusals: int = 0

    def price_for(self, model: str) -> ModelPrice:
        """Return the price for ``model`` or raise :class:`BudgetUnpriced`."""
        if self.override is not None:
            return self.override
        price = pricing.lookup_price(model, self.prices)
        if price is None:
            raise BudgetUnpriced(
                f"no price for model {model!r}; supply an explicit price override "
                f"or add it to the pricing table before a paid run"
            )
        return price

    def check(self, request: Any) -> float:
        """Price the worst case for ``request`` and refuse if it risks the budget.

        Returns the worst-case dollar cost of this single call when it is safe to
        proceed. Raises :class:`BudgetUnpriced` if the model has no price, or
        :class:`BudgetExceeded` (and increments :attr:`refusals`) if the call
        could push cumulative spend over ``max_cost_usd``. Call this *before*
        contacting the client.
        """
        price = self.price_for(request.model)
        worst_case = pricing.cost_usd(
            price, request.estimated_input_tokens(), request.max_tokens
        )
        projected = self.spent_usd + worst_case
        if projected > self.max_cost_usd + _EPSILON:
            self.refusals += 1
            raise BudgetExceeded(
                f"refusing call: worst-case ${worst_case:.4f} on top of spent "
                f"${self.spent_usd:.4f} would reach ${projected:.4f}, over the "
                f"${self.max_cost_usd:.4f} budget"
            )
        self.projected_usd = max(self.projected_usd, projected)
        return worst_case

    def record(self, response: Any) -> float:
        """Add ``response``'s actual usage to the running totals; return its cost.

        A cached response (``response.cached``) is free and is *not* recorded —
        it neither cost money nor consumed budget this run.
        """
        if getattr(response, "cached", False):
            return 0.0
        price = self.price_for(response.model)
        cost = pricing.cost_usd(price, response.input_tokens, response.output_tokens)
        self.spent_usd += cost
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        self.calls += 1
        return cost

    def remaining_usd(self) -> float:
        """Budget left before the ceiling (never negative)."""
        return max(0.0, self.max_cost_usd - self.spent_usd)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_usd": round(self.max_cost_usd, 6),
            "spent_usd": round(self.spent_usd, 6),
            "projected_usd": round(self.projected_usd, 6),
            "remaining_usd": round(self.remaining_usd(), 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "calls": self.calls,
            "refusals": self.refusals,
            "override": self.override.to_dict() if self.override is not None else None,
        }
