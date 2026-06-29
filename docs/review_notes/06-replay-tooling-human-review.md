Human review: Milestone 6 — Replay and debugging tools

TL;DR
Adds trace inspection and replay tooling. `replay_trace(trace)` reconstructs a
run from a stored Milestone 5 trace — *without re-executing anything* — into a
`ReplayedRun`: the action timeline, the tool calls, the tests, the diff, the
detected anomalies, and the single failure point that best explains the verdict.
`summarize_trace` renders it as a compact text summary; `trace_to_markdown`
renders a fuller Markdown report. The CLI surface is `trace show <path>`
(text / `--json`) and `trace report <path>` (stdout / `--out`). Covered by
`tests/test_replay.py`; all 192 tests pass.

What changed
- Added `src/code_agent_runtime/traces/replay.py` (`ReplayedRun`, `ToolCallView`,
  `Anomaly`, `ANOMALY_KINDS`, `replay_trace`).
- Added `src/code_agent_runtime/traces/summarize.py` (`summarize_trace`,
  `trace_to_markdown`).
- Re-exported the new API from `traces/__init__.py`.
- Added CLI `trace show` / `trace report`; `info` now reports Milestone 6.
- Added `/logs/` to `.gitignore` (milestone runner's local logs).
- Added `tests/test_replay.py`; extended `tests/test_scaffold_layout.py`.
- Updated `site/tracing-replay.html`, `site/index.html`, `site/architecture.html`,
  `site/roadmap.html`, `docs/ARCHITECTURE.md`, `README.md`.

What should be checked later
- Reconstruction, not re-execution. Replay reads the trace and interprets it; it
  does not re-run commands. Confirm that is the intended scope for now (a true
  re-execution/verification mode is a later, optional capability), and that
  everything replay needs is present in the trace (timeline events + embedded
  result). Where both exist, replay prefers the embedded `result` (full payload)
  and falls back to the compact event.
- Failure-point policy. Anomalies = every problem signal (blocked tool, tool
  error, failed tests, run error) in timeline order. `failure_point` = the one
  explaining the verdict: `run_error`, then `tests_failed`, else the earliest
  anomaly. A run that **passed or was not scored has no failure point even if it
  logged anomalies**. Confirm this asymmetry is what you want — it is deliberate,
  to surface verdicts that hid a failure mode (a research-question case), and is
  asserted by a test (a blocked tool on a passing run is an anomaly, not the
  failure point).
- Counts. `tool_call_count` / `blocked_count` / `failed_tool_count` /
  `command_count` are derived from the timeline, not read from the embedded
  result, so a replay can be cross-checked against the original `RunResult`.
  Confirm the `command_count` definition (allowed `run_shell`/`run_tests` agent
  calls) still matches the runtime's `_COMMAND_TOOLS`.
- Markdown rendering. Table cells escape `|`; the test output is tailed
  (last ~20 lines) and the unified diff is capped (~200 lines) with an explicit
  "N lines omitted" note. Confirm the caps and the "no failure point" / "Failure
  point" phrasings read well in your target (PR comment, archived record).
- Redaction. Rendered output is **not** redacted — a report contains whatever the
  trace stored, including raw command output. Same limitation as the recorder;
  redaction is Milestone 7. Do not publish reports of untrusted runs before then.
- CLI exit codes. `trace show` / `trace report` are inspectors: they return 0 on
  success and 1 only when the trace file is missing/malformed — they do **not**
  mirror the run's pass/fail verdict. Confirm that is the behaviour you want (vs.
  a CI gate that exits non-zero on a failed run).

Technical risks
- Low. No new dependency; pure data in, strings out; no subprocess, filesystem
  mutation (other than `trace report --out`), or network. The main caveats are
  the unredacted-output limitation (shared with the recorder) and that replay
  trusts a trace this runtime wrote — `from_dict` validates shape, not full
  semantics, so a hand-edited trace could produce odd output.

Commands to verify
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --trace traces/`
- `PYTHONPATH=src python3 -m code_agent_runtime trace show traces/<id>.trace.json`
- `PYTHONPATH=src python3 -m code_agent_runtime trace show traces/<id>.trace.json --json`
- `PYTHONPATH=src python3 -m code_agent_runtime run bugfix/sum-range-off-by-one --agent mock --trace /tmp/f.trace.json`
  then `... trace report /tmp/f.trace.json` (shows the tests_failed failure point)
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
