Human review: Milestone 0 — Scaffold and project foundations

TL;DR
First milestone. Creates the package skeleton, CLI, packaging, docs skeleton,
multi-page website, and a CPU-only smoke test. No runtime/tools/sandbox/tracing
logic yet. Default tests are free and require no paid API.

What changed
- Added `src/code_agent_runtime/` (package, CLI, `__main__`).
- Added `pyproject.toml`, `conftest.py`, `README.md`, `LICENSE`.
- Added `tests/test_smoke.py` and `tests/test_scaffold_layout.py`.
- Added docs skeleton: ARCHITECTURE, METHODOLOGY, SECURITY_MODEL, LIMITATIONS,
  RESULTS, REPRODUCIBILITY, RESEARCH_QUESTIONS.
- Added multi-page static website under `site/` (10 pages + `style.css`).
- Added milestone/commit/review notes under `docs/`.

What should be checked later
- Whether the `conftest.py` path shim should be replaced by a mandatory
  editable install once CI exists.
- Whether the console-script entry point behaves correctly after a real install
  (`pip install -e .`), which was not exercised here because `python3-venv` is
  unavailable in this environment.
- Website copy for accuracy as real subsystems land.

Technical risks
- Low. No execution surface beyond a read-only CLI. No network, no API calls.
- The CLI's `info` text hard-codes the current/next milestone strings; these
  must be kept in sync as milestones progress.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime --help`
- `PYTHONPATH=src python3 -m code_agent_runtime info`
- `PYTHONPATH=src python3 -m code_agent_runtime version`

Human feedback
<!-- Human will fill this later. -->
