# Commit note — Milestone 6

**Commit message:** `Add trace inspection and replay tooling`

## What this commit adds

- `src/code_agent_runtime/traces/replay.py` — reconstruct a run from a stored
  trace **without re-executing** it:
  - `ReplayedRun` (timeline, tool calls, tests, diff, anomalies, failure point,
    counts), `ToolCallView`, `Anomaly`, `ANOMALY_KINDS`.
  - `replay_trace(trace)` — pure reconstruction. The `failure_point` is the
    anomaly that best explains the verdict (`run_error` → `tests_failed` →
    earliest); a run that passed or was not scored has none, even with anomalies.
- `src/code_agent_runtime/traces/summarize.py` — render a reconstruction:
  - `summarize_trace(trace)` — compact text summary.
  - `trace_to_markdown(trace)` — Markdown report (headings + tables, test-output
    tail, capped unified diff; table cells escape pipes).
- CLI: `trace show <path>` (text / `--json`) and `trace report <path>`
  (stdout / `--out PATH`); `info` reports Milestone 6.
- `traces/__init__.py`: re-exports the replay/summarise API.
- `.gitignore`: ignore `/logs/` (milestone runner's local run/cost logs).
- Tests: `tests/test_replay.py`; `tests/test_scaffold_layout.py` extended.
- Docs/site: `site/tracing-replay.html` (replay now implemented), `site/index.html`,
  `site/architecture.html`, `site/roadmap.html`, `docs/ARCHITECTURE.md`,
  `README.md` updated; Milestone 6 milestone/commit/review notes added.

## Excluded (per operating principles)

No secrets, virtualenvs, caches, `node_modules`, weights, or large artifacts. No
new runtime dependency (replay/summarise use only the stdlib). Replay does not
re-execute anything — no workspace, subprocess, or network. Generated traces and
reports are not committed (`/traces/` and `/logs/` are gitignored; tests write to
`tmp_path`). Rendered output is **not** redacted — same limitation as the
recorder (Milestone 7). No paid API is used or required.

## Verification at commit time

- `python3 -m pytest -q` passes (192 tests; git-dependent diff assertions skip if
  `git` is unavailable).
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
  then `trace show` / `trace report` over the written trace reconstruct the
  timeline, tool calls, tests, diff, and (for a failing run) the failure point.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
