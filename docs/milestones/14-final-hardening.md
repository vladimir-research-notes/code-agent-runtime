# Milestone 14 — Final hardening

## Summary

The runtime, tracing, sandbox, scoring, regression, LLM-adapter, importer, case
study, and website all landed in Milestones 0–13. This final milestone does not
add a subsystem; it adds the **gate that keeps the repository releasable** and runs
the plan's final checks: tests, lint, hygiene, docs consistency, website
consistency, no secrets, no huge artifacts, README quality, and reproducibility
instructions.

The deliverable is a single runnable check — `release-check` — that aggregates
those into one structured report, plus a test that asserts the repository passes
every required check (and, just as importantly, unit tests proving each check
actually *fails* on a broken input, so the gate has teeth rather than being a
rubber stamp).

No runtime/scoring/sandbox/tracing/importer behaviour changed. The new code is the
`release` module, its script wrapper, a CLI subcommand, and tests; the rest is the
standard per-milestone documentation/website/notes update.

## What the gate checks

`code_agent_runtime.release.run_release_checks(root)` returns a `ReleaseReport` of
ten checks. Eight are **required** (they gate the verdict); two are **optional**
(advisory, off by default so the gate stays fast, free, and offline):

| Check | Required | What it verifies |
| --- | --- | --- |
| `source_compiles` | yes | every `*.py` under `src/` parses (a free, in-memory stand-in for lint — writes no `.pyc`) |
| `hygiene_clean` | yes | no error-severity findings from `hygiene.scan_repo` (one scan, shared) |
| `no_secrets` | yes | no credential-shaped strings in tracked files |
| `no_large_artifacts` | yes | no committed model weights, oversized files, or result blobs |
| `docs_consistency` | yes | required docs exist; every milestone `0..N` has milestone/commit/review notes; CLI `CURRENT_MILESTONE` equals the latest note |
| `website_consistency` | yes | the ten pages exist, each links the full nav, resolves internal `*.html` links, and references no external URL |
| `readme_quality` | yes | README is substantial, has the expected sections, and its relative links all resolve |
| `reproducibility` | yes | `docs/REPRODUCIBILITY.md` exists and names the reproduce commands (`pytest`, `python3`) |
| `lint` | no | runs `ruff check` when `--with-lint` is passed *and* ruff is installed; otherwise skipped |
| `tests` | no | runs `python3 -m pytest -q` when `--with-tests` is passed; otherwise skipped |

The required set is exactly the plan's "final checks" list. `lint` and `tests` are
optional because the project's operating principles keep the default path free and
dependency-light: ruff is not a declared dependency, and running the full suite
inside the gate would be slow and would recurse if the gate were called from a
test. They are available on demand (`--with-lint` / `--with-tests`) and never fail
the gate when their tool is absent.

## Deliverables

- **`src/code_agent_runtime/release.py`** (new) — the checker: `ReleaseCheck` /
  `ReleaseReport` dataclasses (mirroring the `environment` module's shape), one
  function per check, `run_release_checks`, `format_report`, and a `main` for the
  CLI/script. Pure stdlib; reuses `hygiene.scan_repo`; offline and deterministic.
- **`scripts/08_final_checks.py`** (new) — script wrapper mirroring
  `04_check_repo_hygiene.py`: defaults `--root` to this repo, forwards flags,
  exits non-zero on failure.
- **`src/code_agent_runtime/cli.py`** — a `release-check` subcommand wired to
  `release.main` (`--with-tests`, `--with-lint`, `--strict`, `--json`); the top
  docstring extended for Milestone 14; `CURRENT_MILESTONE` 13→14 and
  `NEXT_MILESTONE` advanced to "all planned milestones complete".
- **`tests/test_release.py`** (new) — asserts the real repo passes every required
  check, and that each check *fails* on a deliberately broken minimal fixture
  (missing doc, broken README link, external-URL page, syntax error, planted
  secret, large file). Also asserts `--with-tests`/`--with-lint` stay skipped by
  default and that `run_release_checks` never shells out to pytest implicitly.
- **`tests/test_scaffold_layout.py`** — extended for the Milestone 14 notes.
- **Website** — `index`, `architecture`, `limitations`, and `roadmap` updated to
  mark Milestones 13 and 14 done, add `release.py` / `scripts/08_final_checks.py`
  to the relevant-files lists, and refresh the global status badges; a short
  "Final hardening (Milestone 14)" note where each page narrates milestones.
- **Docs** — `docs/LIMITATIONS.md` status line 12→14; this milestone note, the
  commit note, and the human-review placeholder.

## Design notes / decisions

- **Teeth, not a rubber stamp.** A consistency check that can never fail is
  worthless. `tests/test_release.py` therefore builds a deliberately broken
  minimal repo for each check and asserts the check flips to *fail* — so the gate
  is proven to detect a missing doc, a broken link, an external asset, a syntax
  error, and a planted credential.
- **One hygiene scan, three checks.** `no_secrets`, `no_large_artifacts`, and
  `hygiene_clean` are derived from a single `scan_repo` pass rather than scanning
  three times. The milestone lists them separately, so the report does too.
- **The gate found a real inconsistency.** Bumping `CURRENT_MILESTONE` to 14
  before the notes existed made `docs_consistency` fail with "CLI is 14 but the
  latest note is 13" — exactly the drift the check is meant to catch. It passed
  only once the M14 notes were written, which is the intended workflow.
- **No new dependency.** Lint reuses whatever `ruff` is on `PATH` if asked;
  `source_compiles` is the always-available, in-memory syntax gate so "lint"
  has a free, deterministic floor.

## Honest limitations

- `release-check` is a **structural** gate. It verifies that sections, links,
  notes, and constants are present and consistent and that tracked files are
  clean — it does not validate prose accuracy, render the website, or prove the
  documentation describes the code correctly. Content correctness still relies on
  review.
- `source_compiles` checks that modules parse, not that they are correct or
  warning-free; it is a syntax floor, not a type checker or linter.
- `no_secrets` / `no_large_artifacts` inherit the hygiene scanner's heuristics:
  high-precision secret patterns can miss novel or obfuscated credentials, and
  the scan covers tracked files only.
- The optional `tests`/`lint` checks are advisory: a green `release-check` with
  both skipped does **not** assert the suite passed — run `--with-tests` (or
  `python3 -m pytest -q`) for that.

## Validation

- `python3 scripts/08_final_checks.py` — all eight required checks pass; the two
  optional checks report skipped. Exit 0.
- `python3 scripts/08_final_checks.py --with-tests --with-lint` — also runs the
  suite and ruff-if-present.
- `python3 -m pytest -q` — full CPU-only suite passes, including the new
  `tests/test_release.py`. No model, network, or key.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.
- `PYTHONPATH=src python3 -m code_agent_runtime release-check --strict` — the same
  gate via the CLI.

## Status

Complete. This is the final milestone of the plan; no further milestones are
planned (`docs/PLAN.md`).
