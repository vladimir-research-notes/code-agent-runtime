"""Command-line interface for Code Agent Runtime.

The CLI is intentionally minimal at this stage. It exposes version/status
commands plus the Milestone 1 operational checks (``env-check``, ``hygiene``).
Task running, tracing, replay, scoring, and reporting subcommands are added in
later milestones (see ``docs/PLAN.md``).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import PROJECT_NAME, PROJECT_SUMMARY, __version__
from . import environment as _environment
from . import hygiene as _hygiene

# The milestone the runtime currently implements. Kept here so ``info`` can
# report honest project status without scanning the filesystem.
CURRENT_MILESTONE = "Milestone 1 — Environment and repository hygiene"
NEXT_MILESTONE = "Milestone 2 — Versioned task format"


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

    p_env = subparsers.add_parser(
        "env-check",
        help="Check the host satisfies the runtime's CPU-only, no-paid-API requirements.",
    )
    p_env.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    p_env.set_defaults(func=_cmd_env_check)

    p_hyg = subparsers.add_parser(
        "hygiene",
        help="Scan tracked files for secrets, junk, and large/binary artifacts.",
    )
    p_hyg.add_argument("--root", default=".", help="Repository root to scan (default: cwd).")
    p_hyg.add_argument(
        "--max-bytes",
        type=int,
        default=_hygiene.DEFAULT_MAX_BYTES,
        help="Large-file threshold in bytes.",
    )
    p_hyg.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also scan untracked, non-gitignored files.",
    )
    p_hyg.add_argument("--strict", action="store_true", help="Treat warnings as failures too.")
    p_hyg.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    p_hyg.set_defaults(func=_cmd_hygiene)

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


def _cmd_env_check(args: argparse.Namespace) -> int:
    return _environment.main(["--json"] if args.json else [])


def _cmd_hygiene(args: argparse.Namespace) -> int:
    forwarded = ["--root", args.root, "--max-bytes", str(args.max_bytes)]
    if args.include_untracked:
        forwarded.append("--include-untracked")
    if args.strict:
        forwarded.append("--strict")
    if args.json:
        forwarded.append("--json")
    return _hygiene.main(forwarded)


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
