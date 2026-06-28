# Code Agent Runtime

A local-first runtime for **running, tracing, sandboxing, replaying, and
evaluating coding agents** under controlled conditions.

This is an independent systems/research platform for understanding the runtime
infrastructure *around* coding agents — task setup, tools, permissions,
execution, tracing, replay, scoring, regression comparison, and reports. It is
**not** a tutorial, a clone of a commercial tool, or a benchmark leaderboard.

> Status: **Milestone 1 — Environment and repository hygiene.** This repository
> is being built milestone by milestone (see [`docs/PLAN.md`](docs/PLAN.md)). The
> package, docs, website, packaging, and tests exist, plus an environment check
> and a repository hygiene scanner. The agent runtime itself (tasks, tools,
> execution, tracing, scoring) is not yet implemented.

## Design constraints

- CPU-first; runs on a general instance (e.g. `m5.2xlarge`). No GPU required.
- **No paid LLM API calls in tests.** Mock and scripted agents are first-class.
- Claude API / Claude Code integration is optional, disabled by default, and
  cost-guarded — added only after the runtime foundations exist.
- No secrets, virtualenvs, caches, `node_modules`, model weights, or large
  generated artifacts are committed.
- Honest about security limitations: this is **not** a production-grade sandbox.

## Repository layout (target)

```
src/code_agent_runtime/   # Python package (CLI today; subsystems land per milestone)
tasks/                    # versioned coding-agent task definitions
examples/                 # tiny reproducible example repos
results/                  # eval outputs (raw / processed / reports)
docs/                     # plan, architecture, methodology, security, results
site/                     # multi-page static website
scripts/                  # environment / smoke / report / site / hygiene helpers
tests/                    # CPU-only, free tests
```

See [`docs/PLAN.md`](docs/PLAN.md) for the full target layout and milestone plan.

## Quick start

This environment uses `python3` (Python 3.10+). The core package has **no
runtime dependencies**; only the test runner (`pytest`) is needed for the suite.

```bash
# Run the CLI (no install required thanks to the src/ layout + conftest path):
PYTHONPATH=src python3 -m code_agent_runtime --help
PYTHONPATH=src python3 -m code_agent_runtime info

# Run the test suite (pytest must be available):
python3 -m pytest -q
```

### Operational checks (Milestone 1)

Two read-only, offline checks enforce the project's CPU-only / no-committed-junk
principles:

```bash
# Is this host able to build and test the runtime, offline and free?
python3 scripts/00_check_environment.py
PYTHONPATH=src python3 -m code_agent_runtime env-check --json

# Does any tracked file contain a secret or junk that shouldn't be committed?
python3 scripts/04_check_repo_hygiene.py            # scans this repo
PYTHONPATH=src python3 -m code_agent_runtime hygiene --root . --strict
```

The hygiene scanner inspects **git-tracked files** (filesystem-walk fallback
outside a git work tree) for secrets, virtualenvs, caches, `node_modules`, large
files, result blobs, model weights, and a committed local Claude settings file.
Secret detection is heuristic; see [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

Optionally install the package and dev extras in a virtual environment:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
code-agent-runtime info
pytest -q
```

See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for details and known
environment caveats.

## Documentation

| Doc | Purpose |
| --- | --- |
| [`docs/PLAN.md`](docs/PLAN.md) | Thesis, constraints, non-goals, milestones. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System components and data flow. |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | How agents are evaluated. |
| [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) | Threat model and sandbox limits. |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | What is and isn't proven. |
| [`docs/RESULTS.md`](docs/RESULTS.md) | Result tables (empty until evals run). |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | How to reproduce runs. |
| [`docs/RESEARCH_QUESTIONS.md`](docs/RESEARCH_QUESTIONS.md) | Questions this platform probes. |

A multi-page static website lives under [`site/`](site/) — open
`site/index.html` in a browser.

## License

MIT. See [`LICENSE`](LICENSE).
