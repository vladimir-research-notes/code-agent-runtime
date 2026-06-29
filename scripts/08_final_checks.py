#!/usr/bin/env python3
"""Run the final-hardening checks over this repository (Milestone 14).

Thin wrapper around :mod:`code_agent_runtime.release`. Defaults to checking this
repository (the directory above ``scripts/``) so it works regardless of the
current working directory. Exits non-zero if any *required* check fails (or, with
``--strict``, if an optional check that ran failed).

    python3 scripts/08_final_checks.py [--with-tests] [--with-lint] [--strict] [--json]

By default the optional ``lint`` (ruff) and ``tests`` (pytest) checks are skipped
so the gate stays fast and offline; pass ``--with-lint`` / ``--with-tests`` to run
them.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime.release import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    # Default to checking this repository unless an explicit --root was given.
    if not any(arg == "--root" or arg.startswith("--root=") for arg in argv):
        argv = ["--root", str(ROOT), *argv]
    raise SystemExit(main(argv))
