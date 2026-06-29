"""Tests for ``slugify`` (task fixture).

These fail against the unimplemented stub (it raises ``NotImplementedError``) and
pass once ``slugify`` lower-cases, splits on whitespace, and joins with hyphens.
They define the success condition for ``tests/implement-slugify``.
"""

from slugify import slugify


def test_basic() -> None:
    assert slugify("Hello World") == "hello-world"


def test_trims_and_collapses_whitespace() -> None:
    assert slugify("  Multiple   Spaces ") == "multiple-spaces"


def test_keeps_existing_hyphens_and_digits() -> None:
    assert slugify("Already-slug 123") == "already-slug-123"
