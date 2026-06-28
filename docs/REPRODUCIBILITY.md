# Reproducibility

> **Status:** current as of Milestone 0. Covers building and testing the
> scaffold. Run-level reproducibility (tasks, traces, evals) is documented as
> those milestones land.

## Environment

- OS: Linux (developed on Ubuntu; should work on any POSIX system).
- Python: 3.10+ (this environment ships `python3` 3.12; there is no bare
  `python` shim, so commands below use `python3`).
- No GPU. CPU-only. Suitable for a general instance such as `m5.2xlarge`.
- The core package has **no runtime dependencies**. The only test dependency is
  `pytest`.

## Get the code running

The `src/` layout plus the repo-root `conftest.py` path shim means you can run
the package and tests without installing anything beyond `pytest`:

```bash
# CLI
PYTHONPATH=src python3 -m code_agent_runtime --help
PYTHONPATH=src python3 -m code_agent_runtime info
PYTHONPATH=src python3 -m code_agent_runtime version

# Tests (CPU-only, no network, no paid API)
python3 -m pytest -q
```

### Editable install (optional)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
code-agent-runtime info
pytest -q
```

> Note: creating a virtualenv requires the `python3-venv` package on
> Debian/Ubuntu. If it is unavailable, use the `PYTHONPATH=src` form above and
> install `pytest` with `pip install --user pytest`.

## Determinism policy

- Default tests are deterministic and free.
- No test performs network I/O or paid API calls.
- Future agent runs record enough state in their traces to be replayed.

## What is reproducible today

- Building the package metadata and running the CLI.
- The smoke and scaffold-layout test suites.

## What is not reproducible yet

- Agent runs, traces, evaluations, and result tables (later milestones).

## Relevant files

- `pyproject.toml`, `conftest.py`, `tests/`
- `docs/METHODOLOGY.md`, `docs/RESULTS.md`
