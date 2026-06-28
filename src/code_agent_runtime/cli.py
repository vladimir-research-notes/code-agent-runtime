"""Command-line interface for Code Agent Runtime.

The CLI is intentionally minimal at the scaffold stage. It exposes version and
project-status commands so that the package is runnable and self-describing.
Task running, tracing, replay, scoring, and reporting subcommands are added in
later milestones (see ``docs/PLAN.md``).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import PROJECT_NAME, PROJECT_SUMMARY, __version__

# The milestone the scaffold corresponds to. Kept here so ``info`` can report
# honest project status without scanning the filesystem.
CURRENT_MILESTONE = "Milestone 0 — Scaffold and project foundations"
NEXT_MILESTONE = "Milestone 1 — Environment and repository hygiene"


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="code-agent-runtime",
        description=PROJECT_SUMMARY,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "This is a research/engineering scaffold. Most subcommands are "
            "added in later milestones; run `code-agent-runtime info` for "
            "current status."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    p_version = subparsers.add_parser(
        "version",
        help="Print the runtime version and exit.",
    )
    p_version.set_defaults(func=_cmd_version)

    p_info = subparsers.add_parser(
        "info",
        help="Print project name, summary, and current milestone status.",
    )
    p_info.set_defaults(func=_cmd_info)

    return parser


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _cmd_info(_args: argparse.Namespace) -> int:
    print(f"{PROJECT_NAME} {__version__}")
    print(PROJECT_SUMMARY)
    print()
    print(f"Status : {CURRENT_MILESTONE}")
    print(f"Next   : {NEXT_MILESTONE}")
    print()
    print("Docs   : see docs/PLAN.md and the site/ website.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code.

    With no subcommand, prints help and returns 0 so the bare invocation is
    informative rather than an error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
