# Commit note — Milestone 11

**Commit message:** `Add Claude Code trace importer`

## What this commit adds

- `src/code_agent_runtime/importers/` — the best-effort importer:
  - `schema.py` — `ImportedRun`/`ImportedAction` (JSON round-trip + strict
    validation), `IMPORT_SCHEMA_VERSION`, `SOURCE_KINDS`, `ACTION_KINDS`,
    `TOOL_NAME_MAP`/`TOOL_CATEGORY`, `map_tool_name`, `ImportSourceError`.
  - `diffs.py` — `tree_diff` (content maps → `git_diff`-shaped dict),
    `parse_unified_diff` (raw diff text → same shape). Pure, no `git` dependency.
  - `sources.py` — `import_before_after`, `import_diff_and_log`,
    `import_transcript`, `synthesize_import`, `export_run`, `read_tree`,
    `load_import_source`/`write_import_source`.
  - `convert.py` — `import_to_run`, `ImportOutcome`, `can_verify`; trust/verify
    evidence, step synthesis, canonical trace construction via `TraceRecorder`.
  - `__init__.py` — the subpackage's public surface.
- `cli.py` — `import` command group (`synthesize` / `before-after` / `show` /
  `run` with `--mode auto|verify|trust`, `--trace`, `--report`, `--no-tests`,
  `--json`); `_cmd_import_*` handlers; `_importers` import; milestone constants
  bumped to 11/12; module docstring updated.
- `scripts/06_import_demo.py` — offline demo (writes gitignored `results/`).
- Tests: `tests/test_importers.py` (26 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 11 notes.
- Docs/site: `docs/RESULTS.md`, `docs/ARCHITECTURE.md`, `docs/METHODOLOGY.md`,
  `docs/LIMITATIONS.md`, `README.md`; `index.html`, `architecture.html`,
  `tracing-replay.html`, `evals.html`, `limitations.html`, `roadmap.html`;
  Milestone 11 milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, API keys, virtualenvs, caches, `node_modules`, weights, or large
artifacts. **No model and no network** anywhere: the importer is entirely offline
and the synthetic path runs a deterministic scripted agent on a CPU-only fixture.
The core runtime stays dependency-free. Generated `results/`, `traces/`, and
`logs/` artifacts remain gitignored; the committed narrative in `docs/RESULTS.md`
is the canonical record.

## Honesty notes

The importer is **best-effort**, and the trust/verify split is deliberate.
*Trust* mode scores the source's declared diff/test result — only as trustworthy
as the source. *Verify* mode is the high-signal path: it reconstructs the
workspace from the imported after-state over the task fixture and re-runs the
task's real test command through this runtime's own tools, so the verdict is this
runtime's measurement, not the source's claim. A test proves the difference: a
broken change with a forged "tests passed" scores `passed` in trust mode but
`failed` in verify mode. Verify needs the after-state and the fixture; diff-only
and transcript-only imports cannot be verified, and `auto` falls back to trust and
says so. Reconstructed diff line-counts are best-effort (matching `--numstat` for
ordinary text changes); verification does not depend on them.

## Verification at commit time

- `python3 -m pytest -q` passes (`tests/test_importers.py` added; 26 cases). No
  model, key, or network. Verify-mode cases skip when `git` is absent.
- `python3 scripts/06_import_demo.py` prints the offline tour (synthesize / trust /
  verify / forged-claim / replay) and exits 0.
- `PYTHONPATH=src python3 -m code_agent_runtime import synthesize
  bugfix/sum-range-off-by-one --out results/raw/src.json`, then `import show
  results/raw/src.json` and `import run results/raw/src.json --trace traces/` —
  synthesize, summarise, convert + score, write a trace.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
