"""Greatest common divisor with a deliberate bug (task fixture).

This is the *before* state for ``bugfix/gcd-modulo-swap``. The Euclidean loop is
correct, but the function returns ``b`` after the loop — and the loop only exits
when ``b`` has reached ``0``, so ``gcd`` always returns ``0``. The fix is to
return ``a`` (the last non-zero remainder). The tests fail until then.
"""

from __future__ import annotations


def gcd(a: int, b: int) -> int:
    """Return the greatest common divisor of ``a`` and ``b``.

    Currently buggy: it returns ``b``, which is always ``0`` once the loop ends.
    """
    while b:
        a, b = b, a % b
    return b  # BUG: loop ends with b == 0; should return a
