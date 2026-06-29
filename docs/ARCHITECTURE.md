# Architecture

> **Status:** Milestone 8. Tasks, tools, the runtime loop, structured run
> tracing, trace replay/summarise tooling, permission policies / sandbox
> controls, and scoring + evaluation reports are implemented; regression
> comparison and optional model adapters are filled in milestone by milestone
> (see [`PLAN.md`](PLAN.md)). The component boundaries below are the design
> target.

## Overview

Code Agent Runtime is structured as a pipeline that turns a *versioned task* and
an *agent* into a *scored, replayable trace*. The pipeline is deliberately
explicit so that every step is inspectable and reproducible.

```
task ──▶ workspace ──▶ agent loop ──▶ tools ──▶ tests ──▶ scoring ──▶ report
                            │            │
                            └── trace recorder (captures every step) ──┘
```

## Components

| Component | Package (target) | Responsibility |
| --- | --- | --- |
| Tasks | `tasks/` | Load and validate versioned task definitions. |
| Runtime | `runtime/` | Agent loop, state machine, context, tool dispatch. |
| Agents | `agents/` | Mock, scripted, human, and optional LLM agents. |
| Tools | `tools/` | Structured file, patch, shell, git, test, search tools. |
| Sandbox | `sandbox/` | Permission policy, secret scanning, runners. |
| Traces | `traces/` | Trace schema, recorder, replay, summarization. |
| Scoring | `scoring/` | Test/file/diff/custom scorers and the suite runner (regression in M9). |
| Reports | `reports/` | Markdown and HTML result reports. |

## Data flow

1. **Load task** — parse a versioned task file (id, prompt, fixture, allowed
   tools, timeout, scoring method, test command, resource limits).
2. **Prepare workspace** — materialize a controlled copy of the fixture repo.
3. **Agent step** — the agent proposes an action (a tool call).
4. **Execute tool** — the runtime gates the call against `allowed_tools` and the
   sandbox policy (Milestone 7), dispatches it, then redacts the result's output.
5. **Run tests** — execute the task's test command in the workspace.
6. **Score** — the loop hands the evidence (test result, captured diff, live
   workspace) to `scoring.score_run`, which dispatches on the task's
   `scoring_method` (`test_command`, `expected_files`, `diff_constraint`,
   `custom`, `none`) and returns a verdict, scored before the workspace is
   cleaned up.
7. **Report** — emit a trace artifact and, for a suite of runs, a Markdown/HTML
   result table (`reports/`) over the `SuiteResult` from `scoring.run_suite`.

## Design principles

- **Deterministic-first.** Mock and scripted agents must produce reproducible
  runs without any model call.
- **Everything is traced.** A run that cannot be replayed from its trace is a
  bug, not a feature.
- **Separation of policy and mechanism.** Tools execute; the sandbox decides
  what is allowed.
- **No hidden cost.** Any path that can spend money is opt-in and guarded.

## Current implementation status

- [x] Python package scaffold (`src/code_agent_runtime/`) and CLI.
- [x] Environment check and repository hygiene scanner (Milestone 1).
- [x] Versioned task format — schema, loader (JSON + optional YAML), fixture
      resolution, example tasks, and `tasks list`/`show` CLI (Milestone 2).
- [x] Tool registry and seven core tools — read/write/patch/shell/git-diff/
      tests/search, with structured results, workspace confinement, and a
      `tools list`/`show` CLI (Milestone 3).
- [x] Local runtime state machine — mock and scripted agents, workspace
      preparation, allowed-tool gating, test execution, minimal scoring, and a
      `run` CLI returning a structured `RunResult` (Milestone 4).
- [x] Structured run tracing — a JSON `Trace` schema (timestamped event timeline
      + embedded result), an opt-in `TraceRecorder` the run loop drives,
      `record_run`/`write_trace`/`load_trace`, and a `run --trace` CLI
      (Milestone 5). Captured output is not redacted yet (Milestone 7).
- [x] Trace replay/debugging tooling — `replay_trace` reconstructs a run from its
      trace (timeline, tool calls, diff, tests, anomalies, failure point) without
      re-executing; `summarize_trace`/`trace_to_markdown` render it; `trace show`
      and `trace report` CLI (Milestone 6).
- [x] Permission policies and sandbox controls — a `SandboxPolicy` (allowed/denied
      paths, command allow/denylist, network flag, runtime/output caps) enforced on
      every agent tool call by default, with a secret scanner that redacts
      credential-shaped output before it enters a trace; an unsafe `probe` agent
      demonstrates blocked-vs-allowed (Milestone 7). Not a jail — command matching
      is by program name, network enforcement is heuristic, no process isolation.
- [x] Scoring and evaluation reports — a `scoring/` layer with all four methods
      (`test_command`, `expected_files`, `diff_constraint`, `custom` + registry),
      a suite runner producing a JSON `SuiteResult`, `reports/` for Markdown/HTML
      tables, an optional `scoring_config` task field, and an `eval run`/`eval
      report` CLI (Milestone 8). Verdicts are evidence-based and reproducible.
- [ ] Regression comparison and optional model adapters — pending later milestones.

## Relevant files

- `src/code_agent_runtime/__init__.py`, `src/code_agent_runtime/cli.py`
- `src/code_agent_runtime/tasks/` (schema, loader, fixtures)
- `src/code_agent_runtime/tools/` (registry, base, seven core tools)
- `src/code_agent_runtime/agents/` (base, mock, scripted, solutions, probes)
- `src/code_agent_runtime/runtime/` (state, execution, agent_loop, report)
- `src/code_agent_runtime/traces/` (schema, recorder, store, replay, summarize)
- `src/code_agent_runtime/sandbox/` (policy, permissions, secret_scanner)
- `src/code_agent_runtime/scoring/` (scorer, test/expected_files/diff/custom, suite)
- `src/code_agent_runtime/reports/` (markdown, html)
- `tasks/`, `examples/` (example task definitions and fixtures)
- `scripts/02_generate_report.py` (run the default suite, write reports)
- `docs/PLAN.md` (target layout and milestones)

## Open questions

- What is the minimal trace schema that still supports faithful replay? The
  Milestone 5 `Trace` (a timestamped event timeline plus the embedded
  `RunResult`) is the current answer; Milestone 6's `replay_trace` confirms the
  event/result split reconstructs the timeline, tool calls, diff, tests, and
  failure point. A re-execution/verification mode (re-running a trace to confirm
  it reproduces) remains a later, optional capability.
- Where should the policy/mechanism boundary sit for shell execution?
- The planned `runtime/context.py` and `runtime/tool_registry.py` were collapsed
  (context is `RunConfig` + `ToolContext`; the registry lives in `tools/`). Keep
  that, or restore the split as the runtime grows?
