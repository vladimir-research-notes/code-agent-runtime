"""A tiny greeting CLI (task fixture).

This is the *before* state for the ``cli/add-shout-flag`` task: it greets a
named person but has no ``--shout`` option yet. The task asks an agent to add
that flag without changing the default behaviour.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="greet", description="Print a greeting.")
    parser.add_argument("name", help="who to greet")
    return parser


def format_greeting(name: str) -> str:
    """Return the greeting for ``name`` (default, non-shouting form)."""
    return f"Hello, {name}!"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(format_greeting(args.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
