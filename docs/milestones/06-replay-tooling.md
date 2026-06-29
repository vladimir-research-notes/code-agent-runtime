# Milestone 6 — Replay and debugging tools

## Summary

Add **trace inspection and replay tooling**: read a stored trace (Milestone 5)
back into a structured, interpreted view of the run, and render it as a text
summary or a Markdown report. *Replay* here means **reconstruction, not
re-execution** — exactly what the plan asks for at this stage. It reconstructs
the action timeline, the tool calls, the diff, the tests, and the **failure
point** without preparing a workspace, dispatching a tool, or running a command.

The value over the raw trace is *interpretation*. A bare pass/fail verdict hides
failure modes that are visible in the timeline — a tool the permission gate
blocked, a tool that returned an error, a test command that failed, a run that
errored before finishing. Replay surfaces these as **anomalies** and picks the
one that best explains the verdict as the run's **failure point**. An anomaly on
a run that still *passed* is exactly the "scores hide failure modes" case from
the project's research questions, and the tooling makes it visible.

## Deliverables

- `src/code_agent_runtime/traces/replay.py`:
  - `ReplayedRun` — the reconstructed view (timeline, tool calls, tests, diff,
    anomalies, failure point, and counts that mirror the runtime's accounting).
  - `ToolCallView` — one reconstructed tool call (with `blocked` / `failed`
    helpers); `Anomaly` — one detected problem; `ANOMALY_KINDS`.
  - `replay_trace(trace)` — pure reconstruction, no re-execution.
- `src/code_agent_runtime/traces/summarize.py`:
  - `summarize_trace(trace)` — a compact one-screen text summary.
  - `trace_to_markdown(trace)` — a fuller Markdown report (headings + tables, the
    test-output tail, and the unified diff).
- CLI: `trace show <path>` (text, or `--json` for the structured `ReplayedRun`)
  and `trace report <path>` (Markdown to stdout, or `--out PATH` to a file).
  `info` now reports Milestone 6.
- Package API: the four replay types, `replay_trace`, `summarize_trace`, and
  `trace_to_markdown` are re-exported from `code_agent_runtime.traces`.
- `.gitignore`: ignore `/logs/` (the milestone runner's local run/cost logs).
- Tests: `tests/test_replay.py`; `tests/test_scaffold_layout.py` extended for the
  Milestone 6 notes.

## What replay reconstructs (vs. the plan's checklist)

| Required item | Where it comes from |
| --- | --- |
| action timeline | `ReplayedRun.timeline` — the trace's ordered `events` |
| tool calls | `ReplayedRun.tool_calls` — extracted from `tool_call` events (with allowed/blocked, ok/failed, exit code) |
| diffs | `ReplayedRun.diff` — the embedded `result.diff` (full unified text), else the `diff_captured` event |
| tests | `ReplayedRun.tests` — the embedded `result.tests`, else the `tests_ran` event |
| failure point | `ReplayedRun.failure_point` — the anomaly that best explains the verdict (`None` if the run passed) |

## Design notes / decisions

- **Reconstruction, not re-execution.** The milestone explicitly does not require
  re-running commands; replay reads the trace and interprets it. Re-executing a
  trace to confirm it reproduces is a later, optional capability.
- **Failure point vs. anomalies.** Anomalies are *every* problem signal in the
  run, in timeline order. The single `failure_point` is the one that explains the
  verdict: a terminal `run_error`, then the scoring `tests_failed`, else the
  earliest anomaly. A run that **passed or was not scored has no failure point**,
  even if it logged anomalies — that asymmetry is the point: it shows a verdict
  that hid a failure mode.
- **Pure, one-directional.** `replay`/`summarize` consume a `Trace` and return
  immutable data / strings; they read no clock and touch no filesystem. They sit
  on top of `runtime.state` (for the `RunOutcome`/`RunPhase` vocabularies) and the
  trace schema, never the reverse.
- **Self-contained counts.** `tool_call_count` / `blocked_count` /
  `failed_tool_count` / `command_count` are derived from the timeline so a replay
  can be cross-checked against the original `RunResult` rather than trusting it.
- **Markdown is report-shaped, not raw.** Table cells escape pipes; the test
  output is tailed and the unified diff is capped, with an explicit "N lines
  omitted" note rather than a silent cut.
- **Redaction is still Milestone 7.** A report renders whatever the trace stored,
  including unredacted command output. Same limitation as the recorder; do not
  publish reports of untrusted runs until the secret scanner lands.

## Validation

- `python3 -m pytest -q` — all tests pass (192). `tests/test_replay.py` covers a
  passing run (timeline, tool calls, counts, no failure point), a failing run
  (mock agent → `tests_failed` is the failure point), an errored run (workspace
  prep failed → `run_error`, two-event timeline), a blocked tool call that is an
  anomaly but **not** the failure point on a passing run, `ReplayedRun.to_dict`
  JSON round-trip, the text/Markdown renderers (including pipe escaping in table
  cells), and the `trace show` / `trace report` CLI (text, `--json`, `--out`, and
  the missing-file error path). Diff assertions skip when `git` is absent.
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
  then `... trace show traces/<id>.trace.json` and `... trace report <...> --out report.md`.

## Status

Complete. Next: Milestone 7 — Permission policies and sandbox controls.
