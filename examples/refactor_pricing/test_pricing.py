"""Tests for ``pricing`` (task fixture).

These pin the *behaviour* the refactor must preserve. They pass before and after
the refactor (extracting the duplicated ``0.07`` into a named constant), so they
verify the change is behaviour-preserving; the diff-scope half of the custom
scorer is what rejects a do-nothing agent.
"""

import pytest

from pricing import price_with_tax, tax_for


def test_tax_for() -> None:
    assert tax_for(100) == pytest.approx(7.0)
    assert tax_for(0) == pytest.approx(0.0)


def test_price_with_tax() -> None:
    assert price_with_tax(100) == pytest.approx(107.0)
    assert price_with_tax(200) == pytest.approx(214.0)
