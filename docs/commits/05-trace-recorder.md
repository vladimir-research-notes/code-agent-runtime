# Commit note — Milestone 5

**Commit message:** `Add structured run tracing`

## What this commit adds

- `src/code_agent_runtime/traces/` — structured run tracing:
  - `schema.py`: `Trace`, `TraceEvent`, `SCHEMA_VERSION`, `TRACE_EVENT_KINDS`
    (pure, JSON-serialisable data; `to_dict`/`from_dict` round-trip).
  - `recorder.py`: `TraceRecorder` (the builder the runtime drives) and `Clock`
    (injectable wall + monotonic time); `default_trace_id`.
  - `store.py`: `record_run` (run + trace), `write_trace`, `load_trace`.
  - `__init__.py`: public API re-exports.
- Runtime: `run_task(..., recorder=None)` emits a timestamped event at each stage
  (workspace prepared, each agent step, tests, diff, score) and finishes the
  recorder before returning. The loop calls duck-typed methods guarded by
  `recorder is not None` — it does not import `traces`.
- CLI: `run --trace [PATH]` records and persists a trace; `info` now reports
  Milestone 5.
- `.gitignore`: ignore `/traces/` (the default `--trace` destination).
- Tests: `tests/test_traces.py`; `tests/test_scaffold_layout.py` extended for the
  Milestone 5 notes.
- Docs/site: `site/tracing-replay.html` (now implemented), `site/index.html`,
  `site/architecture.html`, `site/roadmap.html`, `site/limitations.html`,
  `docs/ARCHITECTURE.md`, `docs/LIMITATIONS.md`, `README.md` updated.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (tracing uses only the stdlib `json`, `time`, `datetime`).
Generated traces are not committed (`/traces/` is gitignored; tests write to a
`tmp_path`). Tracing is opt-in and adds nothing to an untraced run. Captured
command output is **not** redacted — recorded as a limitation (Milestone 7), not
hidden. No paid API is used or required.

## Verification at commit time

- `python3 -m pytest -q` passes (git-dependent trace assertions skip if `git` is
  unavailable).
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
  writes `traces/<id>.trace.json` and reports outcome `passed`.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
