"""A stubbed key/value parser (task fixture).

This is the *before* state for the ``tests/implement-kv-parser`` task: the
function is unimplemented and raises ``NotImplementedError``, so the tests fail.
The task is to implement it so that the tests in ``test_kv_parser.py`` pass.

The intended behaviour (pinned by the tests): parse a comma-separated list of
``key=value`` pairs into a dict, trimming whitespace around keys and values and
ignoring empty entries (so an empty string yields an empty dict).
"""

from __future__ import annotations


def parse_kv(text: str) -> dict[str, str]:
    """Parse ``"a=1, b=2"`` into ``{"a": "1", "b": "2"}``.

    Unimplemented in the fixture; implementing it is the task.
    """
    raise NotImplementedError("implement parse_kv for the tests/implement-kv-parser task")
