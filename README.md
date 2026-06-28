# Code Agent Runtime

A local-first runtime for **running, tracing, sandboxing, replaying, and
evaluating coding agents** under controlled conditions.

This is an independent systems/research platform for understanding the runtime
infrastructure *around* coding agents — task setup, tools, permissions,
execution, tracing, replay, scoring, regression comparison, and reports. It is
**not** a tutorial, a clone of a commercial tool, or a benchmark leaderboard.

> Status: **Milestone 0 — Scaffold and project foundations.** This repository is
> being built milestone by milestone (see [`docs/PLAN.md`](docs/PLAN.md)). At
> this milestone the package, documentation, website, packaging, and a smoke
> test exist; the runtime itself is not yet implemented.

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
