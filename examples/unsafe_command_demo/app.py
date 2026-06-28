"""A benign script for the unsafe-command sandbox demonstration (task fixture).

The point of this fixture is *not* this file — it is a normal, harmless module so
the workspace is a real repo. The task that uses this fixture
(``security/unsafe-command-demo``) instructs the agent to attempt host-escaping
commands; the sandbox (Milestone 7) is what must refuse them.
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    print(add(2, 2))
