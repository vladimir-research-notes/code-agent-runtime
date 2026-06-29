"""Pricing helpers with a duplicated magic number (task fixture).

This is the *before* state for ``refactor/extract-rate-constant``. The tax rate
``0.07`` is hard-coded in two places. The task is to extract it into a single
named constant **without changing behaviour** and **without touching any other
file** — scored by a custom scorer that requires both the tests to keep passing
and the change to stay confined to ``pricing.py``.
"""

from __future__ import annotations


def tax_for(amount: float) -> float:
    """Return the tax owed on ``amount``."""
    return amount * 0.07


def price_with_tax(amount: float) -> float:
    """Return ``amount`` plus its tax."""
    return amount + amount * 0.07
