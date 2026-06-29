# Commit note — Milestone 14

**Commit message:** `Finalize code-agent runtime research platform`

## What this commit adds

- **`src/code_agent_runtime/release.py`** (new) — the final-hardening checker.
  `ReleaseCheck` / `ReleaseReport` dataclasses; one function per check
  (`check_source_compiles`, `check_hygiene_clean`, `check_no_secrets`,
  `check_no_large_artifacts`, `check_docs_consistency`, `check_website_consistency`,
  `check_readme_quality`, `check_reproducibility`, plus optional `check_lint` /
  `check_tests`); `run_release_checks` (one shared hygiene scan), `format_report`,
  and a `main`. Pure stdlib, offline, deterministic.
- **`scripts/08_final_checks.py`** (new) — script wrapper mirroring
  `04_check_repo_hygiene.py`; defaults `--root` to this repo, exits non-zero on a
  required-check failure.
- **`src/code_agent_runtime/cli.py`** — `release-check` subcommand wired to
  `release.main` (`--with-tests` / `--with-lint` / `--strict` / `--json`); the top
  docstring extended for Milestone 14; `CURRENT_MILESTONE` 13→14, `NEXT_MILESTONE`
  → "All planned milestones complete (see docs/PLAN.md)".
- **`tests/test_release.py`** (new) — asserts the repo passes every required
  check, and (the point of the test) that each check *fails* on a broken minimal
  fixture: missing required doc, milestone-note gap, broken README link,
  external-URL page, dropped nav link, a `src/` syntax error, a planted AWS-shaped
  secret, and an oversized file. Also asserts the optional checks stay skipped by
  default and `run_release_checks` does not run pytest implicitly.
- **`tests/test_scaffold_layout.py`** — `test_milestone_notes_present` extended for
  the Milestone 14 milestone/commit/review notes.
- **Website** — `site/index.html`, `site/architecture.html`, `site/limitations.html`,
  `site/roadmap.html`: Milestones 13 and 14 marked done; the global status badges
  refreshed; `release.py` / `scripts/08_final_checks.py` / `tests/test_release.py`
  added to relevant-files lists; a short "Final hardening (Milestone 14)" note
  where pages narrate milestones; roadmap "next" cleared (plan complete).
- **Docs** — `docs/LIMITATIONS.md` status line 12→14; `README.md` status line and a
  "Final hardening (Milestone 14)" subsection documenting `release-check`; the
  Milestone 14 milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, API keys, virtualenvs, caches, `node_modules`, weights, or large
artifacts. The release checker is pure stdlib and offline: it shells out to a tool
only when explicitly asked (`--with-lint` runs `ruff` if present; `--with-tests`
runs `pytest`), never by default, and never fails the gate when a tool is absent.
`source_compiles` compiles in memory and writes no `.pyc`.

## Honesty notes

This milestone is hardening and consistency, **not** new runtime capability — no
scoring/sandbox/tracing/importer code path changed. `release-check` is a
**structural** gate: it checks that sections, links, milestone notes, and the CLI
status constant are present and consistent and that tracked files are clean — it
does not validate prose, render the site, or prove the docs describe the code
correctly. The optional `tests`/`lint` checks are advisory: a green
`release-check` with both skipped does not assert the suite passed. The negative
tests deliberately prove each check can fail, so "the repo is consistent" is
enforced, not asserted.

## Verification at commit time

- `python3 scripts/08_final_checks.py` — eight required checks pass; two optional
  skipped (exit 0).
- `python3 -m pytest -q` — full CPU-only suite passes (adds `tests/test_release.py`).
  No model, key, or network.
- `PYTHONPATH=src python3 -m code_agent_runtime release-check --strict` — passes
  via the CLI.
- `PYTHONPATH=src python3 -m code_agent_runtime info` — prints the Milestone 14 status.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.
