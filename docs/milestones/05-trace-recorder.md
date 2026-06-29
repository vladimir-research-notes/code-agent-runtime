# Milestone 5 — Trace recorder

## Summary

Record every run as a structured, JSON-serialisable **trace**: enough to
reconstruct what the task was, what the agent did, what the runtime observed, and
*when* — without re-executing anything. A trace is the evidence behind a reported
result and the input to the replay/summarise tooling that lands in Milestone 6.

This is also where **wall-clock timing enters the system**. The tools layer
(Milestone 3) and the `RunResult` (Milestone 4) are deliberately timing-free so
they stay deterministic and unit-testable; the trace is the one artifact that is
allowed to be temporal. Tracing is **opt-in**: the runtime loop records only when
a recorder is supplied, so an untraced run is byte-for-byte unchanged.

## Deliverables

- `src/code_agent_runtime/traces/` package:
  - `schema.py` — `Trace`, `TraceEvent`, `SCHEMA_VERSION`, `TRACE_EVENT_KINDS`;
    pure data with `to_dict`/`from_dict` round-trip.
  - `recorder.py` — `TraceRecorder` (the stateful builder the loop drives) and
    `Clock` (injectable wall + monotonic time for deterministic tests);
    `default_trace_id`.
  - `store.py` — `record_run` (run + trace in one call), `write_trace`,
    `load_trace`.
  - `__init__.py` — public API re-exports.
- Runtime integration: `run_task(..., recorder=None)` emits a timestamped event
  at each stage and calls `recorder.finish(result)` before returning. The loop
  never imports `traces`; it calls duck-typed methods guarded by
  `recorder is not None`.
- CLI: `run --trace [PATH]` records a trace and writes it (file if `PATH` ends in
  `.json`, else a directory holding `<trace_id>.trace.json`; default `traces/`).
- `.gitignore`: `/traces/` (the default `--trace` destination) is ignored.
- Tests: `tests/test_traces.py`; `tests/test_scaffold_layout.py` extended for the
  Milestone 5 notes.

## What a trace contains (vs. the plan's checklist)

| Required item | Where it lives in the trace |
| --- | --- |
| task metadata | `trace.task` block (id, title, prompt, scoring, test cmd, tools, fixture, limits) |
| workspace metadata | `trace.workspace` block (root, fixture, git) |
| agent actions | `tool_call` / `agent_finish` events |
| tool calls | `tool_call` events (compact) + full payloads in `trace.result.steps` |
| command stdout/stderr | embedded in `trace.result` (tool result `data`) |
| file diffs | `diff_captured` event (summary) + `trace.result.diff` (full unified diff) |
| test results | `tests_ran` event + `trace.result.tests` |
| timestamps | per-event `timestamp` (wall) + `elapsed_seconds` (monotonic); run-level `started_at` / `finished_at` / `duration_seconds` |
| exit status | `trace.outcome` + `run_finished` event + `trace.result` |

The events form the **timestamped timeline**; the embedded `result` holds the
**full payloads** exactly once, so events stay compact and point into it.

## Design notes / decisions

- **The recorder owns *when*; the loop says *what*.** The loop calls explicit
  lifecycle methods (`start`, `workspace_prepared`, `agent_step`, `tests_ran`,
  `diff_captured`, `scored`, `finish`) at the matching stage. The recorder maps
  each to an event kind + phase and stamps the time. This keeps the loop's
  diff tiny and the phase/kind vocabulary in one place.
- **One-directional dependency.** `traces` depends on `runtime`; `runtime` never
  imports `traces`. `run_task` accepts a duck-typed `recorder` and skips it when
  `None`, so there is no import cycle and no cost to an untraced run.
- **Injectable clock, separate wall vs. monotonic.** Wall-clock time gives
  human-readable timestamps; monotonic time is the correct source for
  `elapsed`/`duration` (immune to system-clock adjustments). A test injects a
  deterministic `Clock` subclass, so traces — including ids and ISO timestamps —
  are fully reproducible.
- **Result stays timing-free.** `record_run` returns the same `RunResult` an
  untraced run would; the trace is built alongside, asserted by
  `test_trace_outcome_matches_untraced_run`.
- **No redaction yet (honest limitation).** Captured command output is stored as
  captured. A trace may therefore contain whatever a command printed. Redaction
  belongs with the secret scanner in Milestone 7; until then, do not persist
  traces of untrusted commands to a shared location. Recorded here and on the
  website rather than papered over.

## Validation

- `python3 -m pytest -q` — all tests pass. `tests/test_traces.py` covers the
  schema round-trip, recorder lifecycle (event order, sequence, elapsed),
  `record_run` over `bugfix/sum-range-off-by-one` (full timeline + embedded
  result + deterministic id/timestamps), the error path (a failed run still
  yields a trace), persistence (`write_trace`/`load_trace`, file and directory),
  and the `run --trace` CLI. Git-dependent assertions (the `diff_captured` event)
  skip when `git` is absent.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
  — scripted agent passes; a `traces/<id>.trace.json` is written (path printed to
  stderr).
- `python3 scripts/04_check_repo_hygiene.py` — repo stays clean (`/traces/` is
  gitignored).

## Status

Complete. Next: Milestone 6 — Replay and debugging tools.
