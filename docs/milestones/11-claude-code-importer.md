# Milestone 11 — Claude Code trace importer

## Summary

A best-effort importer that takes a coding-agent run this runtime did **not**
produce — a Claude-Code-like workflow — and converts it into this runtime's own
:class:`Trace` so it can be **scored with the same scorer and replayed with the
same tools** as a native run. The point is to bring external runs under one
microscope: one verdict mechanism, one trace shape, one set of reports.

Everything ships in a new `importers/` subpackage and is **offline and free**: no
model, no network, no paid API. The synthetic path runs a deterministic scripted
agent on a CPU-only fixture; the other paths only read files and parse text.

The pipeline is two stages:

1. **Normalise** an external record into an `ImportedRun` — the *process* (the
   external tool calls, mapped onto this runtime's tool vocabulary), the *change*
   (a `git_diff`-shaped diff and, when available, the after-state file map), and
   the *declared outcome* (an optional test result the source asserts).
2. **Convert and score** it into a `RunResult` + `Trace` via `import_to_run`, in
   one of two modes:
   - **trust** — score the source's declared diff/test result. Fast, but it
     believes the source. The only option when the import carries no file content.
   - **verify** — reconstruct the workspace by materialising the imported
     after-state over the task's fixture, then run the task's **real** test command
     and capture a **real** git diff with this runtime's own tools, and score
     *that*. This turns "the external agent said its tests passed" into "this
     runtime ran the tests and they passed."

`mode="auto"` (default) verifies when it can (after-state + fixture present) and
falls back to trust otherwise, recording which happened so a report never
overstates its evidence.

## Plan requirements → where they live

| Requirement | Implementation |
| --- | --- |
| Before/after directories | `sources.import_before_after` (+ `diffs.tree_diff`, `read_tree`) |
| Git diff plus command log | `sources.import_diff_and_log` (+ `diffs.parse_unified_diff`) |
| Manually exported transcript | `sources.import_transcript` (Claude-Code tool-name mapping) |
| Synthetic Claude-Code-like trace | `sources.synthesize_import` / `export_run` (deterministic, offline) |
| Convert to this runtime's trace format | `convert.import_to_run` → `RunResult` + `Trace` (via `TraceRecorder`) |
| Score with the same scoring system | `convert.import_to_run` calls `scoring.score_run` (verify or trust evidence) |

## Deliverables

- `src/code_agent_runtime/importers/`:
  - `schema.py` — `ImportedRun`/`ImportedAction` (JSON round-trip, strict
    validation), `IMPORT_SCHEMA_VERSION`, `SOURCE_KINDS`, `ACTION_KINDS`,
    `TOOL_NAME_MAP`/`TOOL_CATEGORY`, `map_tool_name`, `ImportSourceError`.
  - `diffs.py` — `tree_diff` (content maps → `git_diff`-shaped dict via
    `difflib`), `parse_unified_diff` (raw diff text → same shape). Pure,
    dependency-free (no `git`).
  - `sources.py` — the four builders, `export_run`, `read_tree`,
    `load_import_source`/`write_import_source`.
  - `convert.py` — `import_to_run`, `ImportOutcome`, `can_verify`; trust/verify
    evidence gathering, step synthesis, and canonical trace construction.
  - `__init__.py` — the subpackage's public surface.
- `cli.py` — `import` command group: `synthesize`, `before-after`, `show`, `run`
  (`--mode auto|verify|trust`, `--trace`, `--report`, `--no-tests`, `--json`);
  `_cmd_import_*`; milestone constants bumped to 11/12.
- `scripts/06_import_demo.py` — offline tour: synthesize → trust → verify →
  forged-claim (verification catches a lie) → replay (writes gitignored
  `results/`).
- Tests: `tests/test_importers.py` (26 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 11 notes.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`; website `index.html`, `architecture.html`,
  `tracing-replay.html`, `evals.html`, `limitations.html`, `roadmap.html`.

## Design notes / decisions

- **Process and evidence are separate layers.** The imported tool calls become the
  trace's steps in *both* modes (faithful to the source); only the *evidence* (the
  tests/diff that drive the score) differs between trust and verify. So a verify
  run reports the external agent's process but this runtime's verdict.
- **Verification is the honest core.** It does not trust the source's claim — it
  rebuilds the fixture as the baseline, overlays the after-state, and runs the
  task's actual test command through the same tools a native run uses. A test in
  `test_importers.py` proves the consequence: a broken change carrying a forged
  "tests passed" scores `passed` in trust mode but `failed` in verify mode.
- **The synthetic path is also the round-trip test.** `synthesize_import` runs the
  scripted solution, snapshots the after-state, and exports the run; importing and
  scoring it reproduces the native run's verdict and tool-call count. This is the
  "synthetic imported run works" validation, and it doubles as a parity check
  (native run → export → import → same outcome).
- **One diff shape, two producers.** `tree_diff` and `parse_unified_diff` both emit
  the exact `git_diff` dict shape (`files[].{path,insertions,deletions}`,
  `untracked`, totals, unified text), so the existing `diff_constraint` scorer and
  the reports consume an imported run unchanged.
- **The canonical trace is built by the real recorder.** `import_to_run` drives the
  same `TraceRecorder` the runtime uses, so the produced trace is byte-for-byte the
  same shape and replays identically (`replay_trace`, `trace show/report`).
- **Tool-name mapping, nothing dropped.** `Read`→`read_file`, `Edit`→`apply_patch`,
  `Bash`→`run_shell`, etc. An unrecognised external tool is kept verbatim and
  surfaced (`ImportedRun.unknown_tools`), never silently dropped.

## Honest limitations (carried into docs)

- **Trust mode is only as trustworthy as its source.** A declared test result is
  the source's claim, not a measurement; only verify mode re-derives it.
- **Verify needs the after-state and the fixture.** Diff-only or transcript-only
  imports carry no file content, so they cannot be verified — `auto` falls back to
  trust and says so. The fixture must be the same baseline the external run started
  from for the reconstructed diff to be meaningful.
- **Reconstructed diff counts are best-effort.** `parse_unified_diff` counts +/-
  lines from the diff text; this matches `git diff --numstat` for ordinary text
  changes but may differ for renames/binary/odd context. Verification does not
  depend on these counts.
- **Text snapshots only.** `read_tree` skips binary/oversized files; binary changes
  are out of scope for these tasks.
- **Verify runs without the sandbox policy.** The reconstruction is this runtime's
  own materialisation (not an untrusted agent), so the test command runs under the
  tool output/time caps but not the path/command policy gate.

## Validation

- `python3 -m pytest -q` — full CPU-only suite passes (`tests/test_importers.py`
  added, 26 cases). No model, no network, no key. Verify-mode cases skip when
  `git` is absent.
- `python3 scripts/06_import_demo.py` — synthesize → trust (passed) → verify
  (passed, replay agrees) → forged claim (trust passed **vs** verify failed). Exit
  0.
- `PYTHONPATH=src python3 -m code_agent_runtime import synthesize
  bugfix/sum-range-off-by-one --out results/raw/src.json` then `import show` /
  `import run --trace ...` — synthesize, summarise, convert + score, write a trace.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 12 — Reproducible case study.
