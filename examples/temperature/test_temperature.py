"""Tests for ``temperature`` (task fixture).

These fail against the inverted-ratio bug and pass once
``celsius_to_fahrenheit`` uses ``9 / 5``. They define the success condition for
``bugfix/temp-convert-ratio``.
"""

from temperature import celsius_to_fahrenheit, fahrenheit_to_celsius


def test_freezing_point() -> None:
    assert celsius_to_fahrenheit(0) == 32


def test_boiling_point() -> None:
    assert celsius_to_fahrenheit(100) == 212


def test_room_temperature() -> None:
    assert celsius_to_fahrenheit(20) == 68


def test_equal_point() -> None:
    # -40 is the temperature at which the two scales coincide.
    assert celsius_to_fahrenheit(-40) == -40


def test_roundtrip_uses_correct_inverse() -> None:
    assert fahrenheit_to_celsius(212) == 100
