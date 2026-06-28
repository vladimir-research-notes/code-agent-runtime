"""Tests for the greet CLI (task fixture).

These assert the *default* behaviour and pass against the before state. The
``cli/add-shout-flag`` task must keep them passing while adding a ``--shout``
flag; a real scored run would extend these tests to cover the new flag.
"""

from greet import format_greeting, main


def test_default_greeting() -> None:
    assert format_greeting("Ada") == "Hello, Ada!"


def test_main_prints_default(capsys) -> None:
    rc = main(["Ada"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "Hello, Ada!"
