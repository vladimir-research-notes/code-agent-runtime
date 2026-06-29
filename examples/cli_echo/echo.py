"""A tiny echo CLI (task fixture).

This is the *before* state for the ``cli/add-reverse-flag`` task: it echoes a
single positional argument and has no ``--reverse`` option. The task adds that
flag (and the matching ``render`` parameter) so that ``--reverse`` prints the
text backwards, while the default behaviour is unchanged.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="echo", description="Echo text.")
    parser.add_argument("text", help="text to echo")
    return parser


def render(text: str) -> str:
    """Return the text to print (default: unchanged)."""
    return text


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(render(args.text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
