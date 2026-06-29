# Code Agent Runtime

A local-first runtime for **running, tracing, sandboxing, replaying, and
evaluating coding agents** under controlled conditions.

This is an independent systems/research platform for understanding the runtime
infrastructure *around* coding agents — task setup, tools, permissions,
execution, tracing, replay, scoring, regression comparison, and reports. It is
**not** a tutorial, a clone of a commercial tool, or a benchmark leaderboard.

> Status: **Milestone 14 — Final hardening (complete). All planned milestones
> (0–14) are done.** This repository was built milestone by milestone (see
> [`docs/PLAN.md`](docs/PLAN.md)).
> The package, docs, website, packaging, and tests exist, plus an environment check, a
> repository hygiene scanner, a versioned task format (schema, loader, example
> tasks, `tasks` CLI), a tool registry with seven structured core tools (`tools`
> CLI), a runtime loop that drives mock and scripted agents over a task (workspace
> preparation, tool gating, test execution, `run` CLI),
> structured run tracing (a JSON trace schema, an opt-in recorder driven by the
> run loop, and `run --trace`), trace replay/debugging tooling (reconstruct a
> run from its trace and render a text summary or Markdown report, via
> `trace show` / `trace report`), permission policies / sandbox controls (a
> `SandboxPolicy` enforced on every agent tool call by default, with output
> redaction, plus an unsafe `probe` agent), scoring + evaluation reports (all
> four scoring methods — `test_command`, `expected_files`, `diff_constraint`,
> `custom` — a suite runner producing a JSON result, Markdown/HTML reports, and an
> `eval` CLI; a real baseline is in [`docs/RESULTS.md`](docs/RESULTS.md)), and
> regression comparison + flakiness analysis (diff two result files into
> improved/regressed/unchanged/flaky buckets, and re-run the suite N times to flag
> non-deterministic keys, via `eval compare` / `eval rerun`), and an optional
> cost-controlled LLM adapter (a model-backed `llm` agent behind a hard pre-call
> budget guard, a response cache, transcript redaction, and a `--dry-run` cost
> preview — offline by default via a deterministic fake client, opt-in to a real
> Claude API run with `--allow-paid`), and a Claude Code trace importer (normalise
> an external, Claude-Code-like run — before/after directories, a diff + command
> log, an exported transcript, or a deterministic synthetic run — into this
> runtime's trace format and score it with the **same** scorer, in *verify* mode by
> re-running the task's real test command or in *trust* mode against the source's
> declared evidence, via the `import` CLI), and a reproducible case study (13 small
> but genuine tasks across all five categories, run by the mock and scripted baselines
> plus the sandbox probes, emitting a result CSV, Markdown/HTML reports, and one
> inspectable trace per run, via `scripts/07_case_study.py` and a `suite_to_csv`
> exporter; the committed table is [`docs/RESULTS.md`](docs/RESULTS.md) and
> [`docs/results/case_study.csv`](docs/results/case_study.csv)).
> Milestone 13 polished the multi-page website — uniform six-section pages,
> consistent status, and self-contained inline-SVG diagrams, enforced by
> `tests/test_site_quality.py`. Milestone 14 adds final hardening: a
> `release-check` gate (`scripts/08_final_checks.py`) that aggregates the
> release-readiness checks — source compiles, hygiene / no-secrets /
> no-large-artifacts, docs consistency, website consistency, README quality, and
> reproducibility, plus optional lint/tests — and a `tests/test_release.py` that
> proves each check fails on a broken input.

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

### Final-hardening gate (Milestone 14)

One aggregated, offline gate runs the project's release-readiness checks and
reports them as a single pass/fail. Eight checks are **required** (they gate the
verdict); two are **optional** and off by default (so the gate stays fast and
needs no extra tooling):

```bash
# Run the final-hardening checks over this repo (exit non-zero on a required failure):
python3 scripts/08_final_checks.py
PYTHONPATH=src python3 -m code_agent_runtime release-check --strict

# Also run ruff (if installed) and the full test suite:
python3 scripts/08_final_checks.py --with-lint --with-tests
```

The required checks are: source compiles, hygiene clean, no secrets, no large
artifacts, docs consistency (every milestone has its three notes and the CLI's
reported milestone matches the latest), website consistency (the ten pages exist,
link the full nav, resolve internal links, and reference no external asset), README
quality (substantial, expected sections, all relative links resolve), and
reproducibility instructions present. `lint` (ruff) and `tests` (pytest) are
optional. This is a **structural** gate — it does not render the site, run a real
linter by default, or prove the docs describe the code; a green `release-check`
with `tests` skipped does **not** assert the suite passed. `tests/test_release.py`
asserts the repo passes every required check *and* that each check fails on a
deliberately broken input.

### Tasks (Milestone 2)

Tasks are versioned, declarative definitions of a single unit of work (canonical
format: JSON `*.task.json`; YAML optional). They are data only — loading one runs
no agent. List and inspect the example tasks:

```bash
PYTHONPATH=src python3 -m code_agent_runtime tasks list --dir tasks
PYTHONPATH=src python3 -m code_agent_runtime tasks show bugfix/sum-range-off-by-one --dir tasks
```

The Milestone 12 case study ships **13 tasks across all five categories** —
bugfix, refactor, cli_change, tests_must_pass, and security — pointing at fixtures
under `examples/` and exercising every scoring method. See
[`tasks/README.md`](tasks/README.md) for the full list and field reference, and
[`docs/RESULTS.md`](docs/RESULTS.md) for the result matrix.

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

Containment is workspace confinement, `allowed_tools` capability gating, and the
Milestone 7 sandbox policy (below). There is still **no** process/namespace
isolation, so do not run a deliberately malicious agent against a real host.

### Sandbox controls (Milestone 7)

Every run enforces a `SandboxPolicy` on each agent tool call by default: allowed/
denied read & write paths, a command allow/denylist, a network flag (default off),
runtime/output caps, and a secret scanner that redacts credential-shaped output
before it enters a step, a trace, or the agent's next observation. A denied call is
recorded as a `blocked` step with the rule that stopped it. The defaults are
permissive (ordinary build/test programs run; `.env`/`.git`/`.aws`/`*.pem` and
host-destructive commands are blocked), so normal runs are unchanged.

The built-in `probe` agent attempts the unsafe actions a coding agent must never
perform; under the default policy the sandbox blocks every one while allowing a
benign in-workspace read:

```bash
# Each unsafe step (read .env, read /etc/shadow, write outside, rm, curl) is blocked:
PYTHONPATH=src python3 -m code_agent_runtime run security/unsafe-command-demo --agent probe

# Disable enforcement (pure allowed_tools gating, no redaction):
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --no-sandbox
```

This reduces blast radius and adds observability — it is **not** a jail. Command
matching is by program name, network enforcement is a heuristic denylist, and
there is no process/namespace isolation. See
[`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

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

With the sandbox enabled (the default), captured command output, file contents,
and diffs are scrubbed of credential-shaped strings before they enter the trace —
using the same heuristic patterns as the hygiene scanner, so redaction can miss
novel or obfuscated secrets. With `--no-sandbox` no redaction occurs. The default
`traces/` destination is gitignored either way.

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
trace, not on a failed run. They render whatever the trace stored, which is
redacted at record time when the sandbox was enabled (Milestone 7).

### Scoring and evaluation reports (Milestone 8)

The runtime scores each run by delegating to a `scoring/` layer that implements
all four methods named by the task schema — `test_command` (tests exit 0),
`expected_files` (files exist / are absent / contain text), `diff_constraint`
(the change stays within `allowed_paths`), and `custom` (a named scorer from an
in-code registry; the shipped `tests_pass_and_diff_scope` combines correctness
with scope) — plus `none` (judged by inspection). Scoring is a pure function of
the evidence a run produced, so verdicts are reproducible.

`eval run` runs a task×agent matrix, scores it, and emits a JSON result and a
Markdown/HTML report (one row per run: task id, agent, pass/fail, runtime, tool
calls, commands, failure reason):

```bash
# Run the whole suite and print a Markdown report:
PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks

# Machine-readable result, or write a result file + an HTML report:
PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --json
PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --out results/raw/eval.json --report results/reports/eval.html

# Re-render a saved result file without re-running anything:
PYTHONPATH=src python3 -m code_agent_runtime eval report results/raw/eval.json

# One-shot: run the default suite and write results/ artifacts:
python3 scripts/02_generate_report.py
```

The deterministic baseline (scripted passes every solvable task; the null mock
agent fails the ones requiring a change) is committed in
[`docs/RESULTS.md`](docs/RESULTS.md). A passing test command is **evidence, not
proof**, of correctness, and `diff_constraint` scores scope, not correctness —
see the caveats there. Generated artifacts under `results/` are gitignored.

### Regression comparison and flakiness analysis (Milestone 9)

Two analyses over the result files above. `eval compare` diffs a baseline result
against a candidate, keyed by `(task_id, agent)`, into
**improved / regressed / unchanged / flaky / added / removed** buckets — *improved*
means the key gained a pass, *regressed* means it lost one. `eval rerun` re-runs
the matrix N times (*rerun mode*) and flags any key whose scored outcome was not
identical on every repeat; the deterministic baseline reports **zero** flaky keys.

```bash
# Re-run the suite 3× and report flaky keys (exit 1 if any flake):
PYTHONPATH=src python3 -m code_agent_runtime eval rerun --dir tasks --repeats 3

# Diff two saved result files (exit 1 if any regression):
PYTHONPATH=src python3 -m code_agent_runtime eval compare base.json cand.json

# One-shot demo: flakiness + a mock→scripted regression comparison:
python3 scripts/03_regression_demo.py
```

A "0 regressions" comparison means *no key lost a pass relative to the baseline* —
not that the candidate is correct. Because the deterministic baseline cannot
regress against itself, the *regressed* and *flaky* buckets are demonstrated on
synthetic "fake agent versions" in `tests/test_regression.py`.

### Optional cost-controlled LLM adapter (Milestone 10)

A model-backed `llm` agent plugs into the same one-action-per-step contract the
deterministic baselines use, wrapped in the safety machinery a paid run requires:
a **hard pre-call budget guard** (it prices each call's worst case — estimated
input plus full `max_tokens` of output — and refuses *before* contacting the model
if that could exceed `--max-cost-usd`), a **response cache** (identical requests
are served free), **transcript redaction** (credential-shaped text is scrubbed
from what is sent to and stored from the model), and a **`--dry-run`** preview that
prints the first request and its estimated cost without making any call.

It is **disabled by default and offline by default**. With no `--allow-paid`, the
agent is driven by a deterministic *fake client* that replays a task's known-good
solution through the model wire format — so the whole path (prompt → parse →
action → tool → score) runs, and the guard/cache/redaction are exercised, with
**no API key and no spend**. A real Claude API run is strictly opt-in.

```bash
# Offline (fake client): solves the task through the model wire format, no API key.
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm

# Dry run: print the first request + estimated worst-case cost; make NO calls.
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm --dry-run
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent llm --dry-run --llm-model claude-opus-4-8

# Offline tour of solve / caching / dry-run / redaction / hard budget stop:
python3 scripts/05_llm_adapter_demo.py

# Real, paid run (opt-in): needs the extra + a key + a budget ceiling.
pip install -e '.[claude]'
export ANTHROPIC_API_KEY=...   # never committed
PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one \
    --agent llm --allow-paid --max-cost-usd 0.25 --llm-model claude-haiku-4-5
```

Pricing in the cost guard is **approximate published list pricing** and must be
verified against current Anthropic pricing before a paid run (it is overridable);
an *unpriced* model is refused rather than guessed. The offline fake replays a
fixed solution — it demonstrates the harness, **not** genuine model reasoning. No
test makes a paid call.

### Claude Code trace importer (Milestone 11)

To compare a Claude-Code-like run against this runtime's agents, that external run
has to be measured the same way. The importer normalises four input forms —
before/after directories, a diff + command log, an exported transcript, or a
deterministic synthetic run — into one import source, then converts it into this
runtime's `Trace` and scores it with the **same** `score_run` as a native run.

The key distinction is **trust vs. verify**. *Trust* mode scores the source's
*declared* diff/test result (fast, but it believes the source). *Verify* mode
reconstructs the workspace from the imported after-state over the task's fixture
and re-runs the task's **real** test command — so the verdict is this runtime's
measurement, not the source's claim.

```bash
# Synthesize a deterministic, offline synthetic Claude-Code-like run for a task:
PYTHONPATH=src python3 -m code_agent_runtime import synthesize \
    bugfix/sum-range-off-by-one --out results/raw/src.json

# Summarise the import source (kind, actions, after-state, declared tests):
PYTHONPATH=src python3 -m code_agent_runtime import show results/raw/src.json

# Convert + score it into a replayable trace (auto: verify if it can, else trust):
PYTHONPATH=src python3 -m code_agent_runtime import run results/raw/src.json --trace traces/
PYTHONPATH=src python3 -m code_agent_runtime import run results/raw/src.json --mode trust

# Build an import source from two directory snapshots (supports verification):
PYTHONPATH=src python3 -m code_agent_runtime import before-after before/ after/ \
    --task bugfix/sum-range-off-by-one --out results/raw/ba.json

# Offline tour: synthesize -> trust -> verify -> a forged claim caught by verify.
python3 scripts/06_import_demo.py
```

The importer is entirely **offline** — no model, no network, no key. Trust mode is
only as trustworthy as its source; verify needs the after-state *and* the task
fixture (diff-only / transcript-only imports fall back to trust and say so). A test
shows the payoff: a broken change carrying a forged "tests passed" scores `passed`
in trust mode but `failed` in verify mode. The synthetic run is a scripted solution
— a harness exercise, not model capability.

### Reproducible case study (Milestone 12)

The case study points the whole platform at a real, if small, workload: **13 tasks
across all five categories** (bugfix, refactor, cli_change, tests_must_pass,
security), each with a deterministic scripted solution or a sandbox probe. It runs
the two baselines the plan names — `mock` (the null baseline) and `scripted` (the
solver) — plus `probe` on the security tasks, with tracing on, and emits the result
CSV, Markdown/HTML reports, and one inspectable trace per run.

```bash
# Run the case study: writes results/raw/case_study.json, results/reports/case_study.{csv,md,html},
# and one trace per run under results/traces/case_study/ (all gitignored), then prints the report:
python3 scripts/07_case_study.py

# Regenerate the committed, deterministic CSV (no machine-dependent runtime column):
python3 scripts/07_case_study.py --canonical-csv docs/results/case_study.csv

# The result table as CSV directly, via the eval CLI (format inferred from .csv):
PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --report out.csv
```

The outcome is the discriminating one the harness should produce: the `scripted`
solver passes every solvable task while the null `mock` baseline fails the ones
that require a change (26 runs — 12 passed, 10 failed, 4 not scored). The
committed, model-free result lives in [`docs/RESULTS.md`](docs/RESULTS.md) and
[`docs/results/case_study.csv`](docs/results/case_study.csv). The *optional*
imported Claude Code run and cost-controlled API run are demonstrated by the M11
importer and M10 LLM-adapter flows above and are intentionally not part of this
committed baseline.

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
| [`docs/RESULTS.md`](docs/RESULTS.md) | Real baseline result table, regression + flakiness, LLM/importer demos (Milestones 8–11). |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | How to reproduce runs. |
| [`docs/RESEARCH_QUESTIONS.md`](docs/RESEARCH_QUESTIONS.md) | Questions this platform probes. |

A multi-page static website lives under [`site/`](site/) — open
`site/index.html` in a browser.

## License

MIT. See [`LICENSE`](LICENSE).
