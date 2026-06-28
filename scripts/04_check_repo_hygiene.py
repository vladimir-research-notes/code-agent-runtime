#!/usr/bin/env python3
"""Run the repository hygiene scan (Milestone 1).

Thin wrapper around :mod:`code_agent_runtime.hygiene`. Defaults to scanning this
repository (the directory above ``scripts/``) so it works regardless of the
current working directory. Exits non-zero if error-severity problems are found.

    python3 scripts/04_check_repo_hygiene.py [--strict] [--json] [--root PATH]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime.hygiene import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    # Default to scanning this repository unless an explicit --root was given.
    if not any(arg == "--root" or arg.startswith("--root=") for arg in argv):
        argv = ["--root", str(ROOT), *argv]
    raise SystemExit(main(argv))
