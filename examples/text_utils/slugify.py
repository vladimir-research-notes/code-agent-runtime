"""A stubbed slugify helper (task fixture).

This is the *before* state for the ``tests/implement-slugify`` task: the function
is unimplemented and raises ``NotImplementedError``, so the tests fail. The task
is to implement it so that the tests in ``test_slugify.py`` pass.

The intended behaviour (pinned by the tests): lower-case the text, split on
runs of whitespace, and join the words with single hyphens.
"""

from __future__ import annotations


def slugify(text: str) -> str:
    """Return a hyphenated, lower-cased slug of ``text``.

    Unimplemented in the fixture; implementing it is the task.
    """
    raise NotImplementedError("implement slugify for the tests/implement-slugify task")
