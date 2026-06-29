Human review: Milestone 11 — Claude Code trace importer

TL;DR
Adds a best-effort importer (new `importers/` subpackage) that converts an
external, Claude-Code-like coding-agent run into this runtime's own `Trace` and
scores it with the **same** scorer as a native run. Four input forms normalise
into one `ImportedRun` (before/after directories, diff+command log, exported
transcript, and a deterministic synthetic run this runtime generates); one
function `import_to_run` converts + scores it into a `RunResult` + `Trace`. Two
modes: **trust** (score the source's declared diff/test result) and **verify**
(reconstruct the workspace from the imported after-state over the task fixture and
re-run the task's real test command). `auto` verifies when it can, else falls back
to trust and records which. Entirely offline (no model, no network, no key);
covered by `tests/test_importers.py` (26 cases); full suite passes.

What changed
- Added `src/code_agent_runtime/importers/` (schema, diffs, sources, convert,
  `__init__`).
- `cli.py`: `import` command group (`synthesize`/`before-after`/`show`/`run`);
  `_cmd_import_*`; milestone constants bumped to 11/12.
- `scripts/06_import_demo.py` (writes gitignored `results/`).
- Tests: `tests/test_importers.py`; extended `tests/test_scaffold_layout.py`.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`, and the website (index, architecture,
  tracing-replay, evals, limitations, roadmap).

What should be checked later
- Trust vs verify framing. Confirm the split is clear everywhere: trust scores the
  source's *claim*; verify re-runs the *real* test command and is the high-signal
  path. The crux test (`test_verify_catches_a_broken_change`) shows a forged
  passing claim → trust `passed`, verify `failed`. Confirm this is the intended
  guarantee and that `auto`'s fallback-to-trust note is prominent enough.
- Verify reconstruction. Verify prepares the task fixture as the git baseline,
  overlays the imported after-state (changed files only; `None` = deletion), then
  runs `run_tests` + `git_diff`. Confirm that materialisation is faithful for your
  use cases, and that requiring the *same fixture baseline* the external run
  started from is an acceptable precondition for a meaningful reconstructed diff.
- Diff reconstruction accuracy. `parse_unified_diff` counts +/- lines from diff
  text; `tree_diff` uses `difflib`. These match `git diff --numstat` for ordinary
  text changes but may differ for renames/binary/odd context. Verification does not
  rely on these counts — confirm that's acceptable for diff-only/trust imports
  where the counts *are* the evidence the `diff_constraint` scorer sees.
- Tool-name mapping. `TOOL_NAME_MAP` maps Claude-Code names (`Read`/`Edit`/`Bash`/
  `Grep`/…) onto runtime tools; unknown names are kept verbatim and surfaced via
  `ImportedRun.unknown_tools`. Confirm the mapping is right (e.g. `Edit`→
  `apply_patch`, `Write`→`write_file`) and that keeping-not-dropping unknowns is
  what you want.
- Transcript parsing. `import_transcript` handles a flat `{"tool","input"}` shape
  and a Claude-Code `content: [{type:"tool_use"}]` block shape; bare text turns
  become `message` actions (preserved in the record but not replayed as runtime
  steps). Confirm both shapes match the transcripts you'd actually import.
- Verify without the sandbox. The reconstruction runs the test command under the
  tool output/time caps but not the sandbox path/command policy gate (it is this
  runtime's own materialisation, not an untrusted agent). Confirm that's the
  intended trust boundary.
- Snapshot scope. `synthesize_import`/`export_run` snapshot only the *changed*
  files as the after-state (read from a kept workspace, then cleaned up); binary/
  oversized files are skipped by `read_tree`. Confirm the snapshot scope is right.
- CLI surface. `import run` resolves the task from `--task` or the source's
  `task_id` (fixture not required up front; trust needs none, verify checks
  availability). Exit codes mirror the verdict (0 passed/not-scored, 1 failed, 2
  error / verify-infeasible). Confirm the surface and codes match intent.

Technical risks
- Low–moderate. The new code is pure and dependency-free (no `git` needed for
  parsing/normalising; `git` is only used by verify's reconstruction, and those
  tests skip when it is absent). The produced trace is built by the same
  `TraceRecorder` the runtime uses and is asserted to round-trip and replay. The
  main interpretive risk is reading a *trust*-mode "pass" as a verified result —
  it is the source's claim; the docs, the `import_to_run` note, and the demo all
  draw the line, and verify mode is the answer when it matters. The synthetic path
  is a scripted solution (a harness/plumbing exercise), not model capability.

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_importers.py -q`
- `python3 scripts/06_import_demo.py`
- `PYTHONPATH=src python3 -m code_agent_runtime import synthesize bugfix/sum-range-off-by-one --out results/raw/src.json`
- `PYTHONPATH=src python3 -m code_agent_runtime import show results/raw/src.json`
- `PYTHONPATH=src python3 -m code_agent_runtime import run results/raw/src.json --trace traces/ --report results/reports/import.md`
- `PYTHONPATH=src python3 -m code_agent_runtime import run results/raw/src.json --mode trust`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
