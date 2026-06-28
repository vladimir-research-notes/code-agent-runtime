# Commit note — Milestone 0

**Commit message:** `Initialize code-agent runtime scaffold`

## What this commit adds

- Python package scaffold under `src/code_agent_runtime/` with a minimal
  argparse CLI (`version`, `info`) and `python -m` support.
- `pyproject.toml` (setuptools, `src/` layout, console script, pytest config).
- Root `conftest.py` path shim for install-free testing.
- CPU-only test suite: `tests/test_smoke.py`, `tests/test_scaffold_layout.py`.
- Documentation skeleton under `docs/` (architecture, methodology, security
  model, limitations, results, reproducibility, research questions).
- Multi-page static website under `site/` (10 pages + `style.css`).
- `README.md` and `LICENSE` (MIT).
- Milestone, commit, and human-review notes under `docs/`.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts.
The partial local `.venv/` (if present) is `.gitignore`d.

## Verification at commit time

- `python3 -m pytest -q` passes.
- `PYTHONPATH=src python3 -m code_agent_runtime --help` and `... info` run.
