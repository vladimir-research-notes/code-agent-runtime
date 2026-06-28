# Milestone 0 — Scaffold and project foundations

## Summary

Establish the project skeleton: a Python package with a minimal CLI, packaging
metadata, a documentation skeleton, a multi-page static website, and a
CPU-only smoke test. No runtime, tools, sandbox, tracing, or scoring yet.

## Deliverables

- `pyproject.toml` — packaging metadata, `src/` layout, console script
  (`code-agent-runtime`), `pytest` config, no runtime dependencies.
- `src/code_agent_runtime/` — `__init__.py` (version + metadata),
  `cli.py` (argparse CLI with `version` / `info`), `__main__.py`.
- `conftest.py` — path shim so the suite runs without an install.
- `tests/test_smoke.py`, `tests/test_scaffold_layout.py` — CPU-only tests.
- `docs/` skeleton: `ARCHITECTURE.md`, `METHODOLOGY.md`, `SECURITY_MODEL.md`,
  `LIMITATIONS.md`, `RESULTS.md`, `REPRODUCIBILITY.md`, `RESEARCH_QUESTIONS.md`.
- `site/` — 10 required static pages plus shared `style.css`.
- `README.md`, `LICENSE` (MIT).

## Validation

- `python3 -m pytest -q` — all tests pass.
- `PYTHONPATH=src python3 -m code_agent_runtime --help` — CLI help works.
- Website files exist (asserted by `tests/test_scaffold_layout.py`).

## Notes / decisions

- The environment provides `python3` only (no bare `python`) and lacks
  `python3-venv`; the `src/` + `conftest.py` approach keeps tests runnable with
  just `pip install --user pytest`. Documented in `REPRODUCIBILITY.md`.
- Core package is intentionally dependency-free to keep default tests free and
  CPU-only.

## Status

Complete. Next: Milestone 1 — Environment and repository hygiene.
