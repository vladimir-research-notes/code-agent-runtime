"""Temperature conversions with a deliberate bug (task fixture).

This is the *before* state for ``bugfix/temp-convert-ratio``. The
Celsius→Fahrenheit conversion uses the inverted ratio ``5 / 9`` instead of
``9 / 5``, so it is wrong for every non-zero input. The accompanying tests fail
until the ratio is corrected. ``fahrenheit_to_celsius`` is already correct and is
included so the fix target (``c * 5 / 9``) is unambiguous.
"""

from __future__ import annotations


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit.

    Currently buggy: the ratio is inverted (``5 / 9``); it should be ``9 / 5``.
    """
    return c * 5 / 9 + 32  # BUG: should be c * 9 / 5 + 32


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius (correct)."""
    return (f - 32) * 5 / 9
