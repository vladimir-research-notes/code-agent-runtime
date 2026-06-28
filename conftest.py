"""Pytest bootstrap for the src/ layout.

Prepends ``src/`` to ``sys.path`` so the test suite imports
``code_agent_runtime`` without requiring an editable install. This keeps the
default test path (``python3 -m pytest``) friction-free and dependency-light,
in line with the project's CPU-only, no-paid-API testing policy.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
