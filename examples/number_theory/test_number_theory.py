"""Tests for ``number_theory.gcd`` (task fixture).

These fail against the ``return b`` bug (which always yields ``0``) and pass once
the function returns ``a``. They define the success condition for
``bugfix/gcd-modulo-swap``.
"""

from number_theory import gcd


def test_common_factor() -> None:
    assert gcd(12, 8) == 4
    assert gcd(54, 24) == 6


def test_coprime() -> None:
    assert gcd(7, 13) == 1


def test_zero_operand() -> None:
    assert gcd(5, 0) == 5
