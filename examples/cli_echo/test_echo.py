"""Tests for the echo CLI (task fixture).

The default-behaviour test passes against the before state; the ``--reverse``
tests fail until the flag (and the ``render(reverse=...)`` parameter) are added.
Together they define the success condition for ``cli/add-reverse-flag``: add the
new behaviour without breaking the default.
"""

from echo import main, render


def test_default_render() -> None:
    assert render("abc") == "abc"


def test_reverse_render() -> None:
    assert render("abc", reverse=True) == "cba"


def test_main_reverse_flag(capsys) -> None:
    rc = main(["--reverse", "abc"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "cba"


def test_main_default(capsys) -> None:
    rc = main(["abc"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "abc"
