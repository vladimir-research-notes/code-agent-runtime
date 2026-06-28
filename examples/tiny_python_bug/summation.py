"""A tiny module with a deliberate off-by-one bug (task fixture).

This is the *before* state for the ``bugfix/sum-range-off-by-one`` task. The
loop excludes ``n``, so ``sum_to(n)`` is one term short of the intended
inclusive sum. The accompanying tests fail until the bug is fixed.
"""

from __future__ import annotations


def sum_to(n: int) -> int:
    """Return the sum of the integers from 1 to ``n`` inclusive.

    Currently buggy: ``range(1, n)`` stops at ``n - 1``, so the final term is
    dropped. The fix is ``range(1, n + 1)``.
    """
    total = 0
    for i in range(1, n):  # BUG: should be range(1, n + 1)
        total += i
    return total
