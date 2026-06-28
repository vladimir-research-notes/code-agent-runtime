"""Tests for ``summation.sum_to`` (task fixture).

These fail against the buggy fixture and pass once the off-by-one is fixed. They
define the success condition for the ``bugfix/sum-range-off-by-one`` task's
``test_command`` scoring method.
"""

from summation import sum_to


def test_sum_to_one() -> None:
    assert sum_to(1) == 1


def test_sum_to_small() -> None:
    assert sum_to(5) == 15
    assert sum_to(10) == 55
