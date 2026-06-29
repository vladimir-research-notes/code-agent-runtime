Human review: Milestone 5 — Trace recorder

TL;DR
Adds structured run tracing. Every run can now be recorded as a JSON-serialisable
`Trace`: task and workspace metadata, a timestamped timeline of agent actions and
tool calls (`events`), and the full embedded `RunResult` (command output, final
diff, test results, exit status). This is where wall-clock timing enters the
system — tools and `RunResult` stay timing-free and deterministic; the trace is
the one temporal artifact. Tracing is opt-in: `run_task(..., recorder=)` records,
and an untraced run is unchanged. `record_run` returns `(result, trace)`;
`write_trace`/`load_trace` persist it; `run --trace [PATH]` is the CLI surface.
Covered by `tests/test_traces.py`.

What changed
- Added `src/code_agent_runtime/traces/` (`schema`, `recorder`, `store`,
  `__init__`).
- Integrated an optional `recorder` into `runtime/agent_loop.py::run_task`
  (events at each stage; `finish` before each return).
- Added CLI `run --trace`; `info` now reports Milestone 5.
- Added `/traces/` to `.gitignore`.
- Added `tests/test_traces.py`; extended `tests/test_scaffold_layout.py`.
- Updated `site/tracing-replay.html`, `site/index.html`, `site/architecture.html`,
  `site/roadmap.html`, `site/limitations.html`, `docs/ARCHITECTURE.md`,
  `docs/LIMITATIONS.md`, `README.md`.

What should be checked later
- Trace schema completeness. Confirm `Trace` carries what Milestone 6 (replay/
  summarise) needs: `task`/`workspace` blocks, ordered `events` with `seq`,
  `phase`, wall `timestamp`, monotonic `elapsed_seconds`, `summary`, `data`; the
  embedded `result`; run-level `started_at`/`finished_at`/`duration_seconds` and
  `outcome`. `SCHEMA_VERSION` is 1; bump on any breaking shape change.
- Event vs. result duplication. `tool_call` events are compact (tool, args,
  allowed, ok, category, exit_code, error); full stdout/stderr/diff live once in
  `trace.result`. Confirm this split is the boundary you want for replay (events =
  timeline pointers, result = payloads), and that nothing replay needs is only in
  events.
- Timestamps. Wall clock (`time.time`) is for human-readable timestamps;
  monotonic (`time.monotonic`) is for elapsed/duration. A `FakeClock` makes tests
  deterministic. Confirm UTC ISO rendering and the `default_trace_id`
  (`<task>-<wall.3f>`) collision policy are acceptable; pass an explicit
  `trace_id` when a hard guarantee is needed.
- Redaction. **Captured command output is not redacted.** A trace may contain
  whatever a command printed (including secrets). This is intentional for now and
  documented (schema docstring, `docs/LIMITATIONS.md`, site); redaction is
  Milestone 7. Confirm you do not persist traces of untrusted commands to a
  shared location before then.
- CLI `--trace` semantics. `PATH` ending in `.json` is a file; any other `PATH`
  (default `traces/`) is a directory written as `<trace_id>.trace.json`. The
  written path is printed to stderr so `--json` stdout stays clean. Confirm the
  default directory and the gitignore entry suit your workflow.

Technical risks
- Low/medium. Tracing adds no new dependency and no behaviour to untraced runs
  (the loop only calls recorder methods when one is passed). The main risk is
  **disk + privacy**: traces embed full command output unredacted and can be
  large; persisting them is the caller's choice (`--trace` / `write_trace`). The
  default destination is gitignored to avoid accidental commits.
- The recorder reads the real clock by default (non-deterministic timestamps in
  production traces) — intended. All tests inject a `FakeClock`, so the suite
  stays deterministic.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
- `PYTHONPATH=src python3 -m code_agent_runtime run cli/add-shout-flag --trace /tmp/x.trace.json --json`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
