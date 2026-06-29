"""Tests for ``parse_kv`` (task fixture).

These fail against the unimplemented stub and pass once ``parse_kv`` splits on
commas, partitions each pair on ``=``, trims whitespace, and ignores empty
entries. They define the success condition for ``tests/implement-kv-parser``.
"""

from kv_parser import parse_kv


def test_basic_pairs() -> None:
    assert parse_kv("a=1,b=2") == {"a": "1", "b": "2"}


def test_trims_whitespace() -> None:
    assert parse_kv("x = 10, y = 20") == {"x": "10", "y": "20"}


def test_empty_string_is_empty_dict() -> None:
    assert parse_kv("") == {}


def test_ignores_trailing_separator() -> None:
    assert parse_kv("k=v,") == {"k": "v"}
