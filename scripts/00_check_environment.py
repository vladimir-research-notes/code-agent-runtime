#!/usr/bin/env python3
"""Run the environment check (Milestone 1).

Thin wrapper around :mod:`code_agent_runtime.environment` so the check can be run
without installing the package. Exits non-zero if a required check fails.

    python3 scripts/00_check_environment.py [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime.environment import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
