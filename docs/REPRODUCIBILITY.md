# Reproducibility

> **Status:** current as of Milestone 1. Covers building and testing the
> package and running the environment / hygiene checks. Run-level
> reproducibility (tasks, traces, evals) is documented as those milestones land.

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

## Operational checks (Milestone 1)

```bash
# Environment check: Python >= 3.10, git, pytest, offline policy.
python3 scripts/00_check_environment.py            # exit 0 if required checks pass
PYTHONPATH=src python3 -m code_agent_runtime env-check --json

# Repository hygiene: secrets / venvs / caches / node_modules / large files /
# result blobs / model weights / committed local Claude settings.
python3 scripts/04_check_repo_hygiene.py           # scans this repo; exit 0 if clean
PYTHONPATH=src python3 -m code_agent_runtime hygiene --root . --strict
```

Both checks are deterministic, read-only, and offline. The hygiene scanner reads
git-tracked files (falling back to a filesystem walk outside a git work tree), so
its output is reproducible from the committed tree.

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
- The environment check and repository hygiene scan.

## What is not reproducible yet

- Agent runs, traces, evaluations, and result tables (later milestones).

## Relevant files

- `pyproject.toml`, `conftest.py`, `tests/`
- `src/code_agent_runtime/environment.py`, `src/code_agent_runtime/hygiene.py`
- `scripts/00_check_environment.py`, `scripts/04_check_repo_hygiene.py`
- `docs/METHODOLOGY.md`, `docs/RESULTS.md`
