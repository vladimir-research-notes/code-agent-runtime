# Code Agent Runtime

A local-first runtime for **running, tracing, sandboxing, replaying, and
evaluating coding agents** under controlled conditions.

This is an independent systems/research platform for understanding the runtime
infrastructure *around* coding agents — task setup, tools, permissions,
execution, tracing, replay, scoring, regression comparison, and reports. It is
**not** a tutorial, a clone of a commercial tool, or a benchmark leaderboard.

> Status: **Milestone 6 — Replay and debugging tools.** This repository is being
> built milestone by milestone (see [`docs/PLAN.md`](docs/PLAN.md)). The package,
> docs, website, packaging, and tests exist, plus an environment check, a
> repository hygiene scanner, a versioned task format (schema, loader, example
> tasks, `tasks` CLI), a tool registry with seven structured core tools (`tools`
> CLI), a runtime loop that drives mock and scripted agents over a task (workspace
> preparation, tool gating, test execution, minimal scoring, `run` CLI),
> structured run tracing (a JSON trace schema, an opt-in recorder driven by the
> run loop, and `run --trace`), and trace replay/debugging tooling (reconstruct a
> run from its trace and render a text summary or Markdown report, via
> `trace show` / `trace report`). The sandbox, full scoring, and reports are not
> yet implemented.

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

### Tasks (Milestone 2)

Tasks are versioned, declarative definitions of a single unit of work (canonical
format: JSON `*.task.json`; YAML optional). They are data only — loading one runs
no agent. List and inspect the example tasks:

```bash
PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks
PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks
```

The three shipped tasks (`bugfix/sum-range-off-by-one`, `cli/add-shout-flag`,
`security/unsafe-command-demo`) point at fixtures under `examples/`. See
[`tasks/README.md`](tasks/README.md) for the full field reference.

### Running a task (Milestone 4)

The runtime drives a deterministic agent over a task and returns a structured,
scored result. It prepares a disposable workspace (a copy of the fixture, never
the committed one), gates each tool call against the task's `allowed_tools`, runs
the task's test command, captures the final diff, and reports. No model, network,
or paid API is involved.

```bash
# Scripted agent: replays a built-in solution and passes the bugfix task.
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one

# Mock agent: the null baseline (does nothing) — leaves the task failing.
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent mock

# Machine-readable result (per-step records, tests, diff, score):
PYTHONPATH=src python3 -m code_agent_runtime run cli/add-shout-flag --json
```

Containment is workspace confinement plus capability gating only — there is **no**
process isolation, resource limit, or network policy yet; that is the sandbox
(Milestone 7). Do not run untrusted tasks against a real host until it lands.

### Tracing a run (Milestone 5)

Any run can be recorded as a structured, JSON-serialisable **trace**: task and
workspace metadata, a timestamped timeline of agent actions and tool calls, and
the full embedded result (command output, the final diff, test results, exit
status). Tracing is opt-in — an untraced run is unchanged.

```bash
# Record a trace into traces/ (written as traces/<trace_id>.trace.json):
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/

# Or to a specific file (the path is printed to stderr):
PYTHONPATH=src python3 -m code_agent_runtime run cli/add-shout-flag --trace /tmp/run.trace.json
```

Captured command output is **not** redacted yet, so a trace may contain whatever
a command printed; do not persist traces of untrusted commands to a shared
location until the secret scanner lands (Milestone 7). The default `traces/`
destination is gitignored.

### Inspecting and replaying a trace (Milestone 6)

`replay` here means **reconstruction, not re-execution**: it reads a stored
trace and rebuilds the action timeline, the tool calls, the diff, the tests, and
the *failure point* — the anomaly (a blocked or failed tool, a failing test
command, a run that errored) that best explains the verdict. A run that passed
but logged an anomaly along the way has none, which is exactly how a verdict can
hide a failure mode.

```bash
# Reconstruct and summarise a trace (text), or emit the structured ReplayedRun:
PYTHONPATH=src python3 -m code_agent_runtime trace show traces/<trace_id>.trace.json
PYTHONPATH=src python3 -m code_agent_runtime trace show traces/<trace_id>.trace.json --json

# Generate a Markdown report (to stdout, or to a file with --out):
PYTHONPATH=src python3 -m code_agent_runtime trace report traces/<trace_id>.trace.json --out report.md
```

`trace show` / `trace report` re-run nothing — no workspace, subprocess, or
network. They are inspectors: they exit non-zero only on a missing or malformed
trace, not on a failed run. Rendered output is **not** redacted either, so the
same don't-publish-untrusted-runs caveat applies until Milestone 7.

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
