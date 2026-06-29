Human review: Milestone 14 — Final hardening

TL;DR
Adds the plan's final-hardening gate: a `release` module + `release-check` CLI
subcommand + `scripts/08_final_checks.py` that aggregate the project's
release-readiness checks (source compiles, hygiene/no-secrets/no-large-artifacts,
docs consistency, website consistency, README quality, reproducibility; optional
lint/tests) into one structured report. Eight checks are required and gate the
verdict; two (lint, tests) are optional and off by default so the gate stays fast,
free, and offline. A new `tests/test_release.py` asserts the repo passes every
required check AND that each check fails on a broken minimal fixture, so the gate
has teeth. No runtime/scoring/sandbox/tracing/importer behaviour changed; the only
non-additive code change is the `info` CLI's two milestone-status strings (13→14)
and the new subcommand. Website + docs updated for M14; full suite passes.

What changed
- `src/code_agent_runtime/release.py` (new): `ReleaseCheck`/`ReleaseReport`, one
  function per check, `run_release_checks` (single shared hygiene scan),
  `format_report`, `main`. Pure stdlib, offline, deterministic.
- `scripts/08_final_checks.py` (new): wrapper mirroring `04_check_repo_hygiene.py`.
- `src/code_agent_runtime/cli.py`: `release-check` subcommand; docstring extended;
  `CURRENT_MILESTONE` 13→14; `NEXT_MILESTONE` → plan-complete.
- `tests/test_release.py` (new); `tests/test_scaffold_layout.py` extended for M14.
- `site/index.html`, `architecture.html`, `limitations.html`, `roadmap.html`:
  M13/M14 marked done; status badges refreshed; release files added to lists;
  a "Final hardening (M14)" note; roadmap "next" cleared.
- `docs/LIMITATIONS.md` status line 12→14; `README.md` status + M14 subsection;
  M14 milestone/commit/review notes.

What should be checked later
- Are the required vs optional check choices right? The plan lists "tests" and
  "lint" among final checks, but this gate makes them optional/advisory (off by
  default) to keep the default path free and dependency-light (ruff is not a
  declared dependency; running pytest inside the gate would be slow and would
  recurse if called from a test). Confirm that trade-off; `--with-tests` /
  `--with-lint` run them on demand. `source_compiles` is the always-on, free
  syntax floor standing in for lint.
- Teeth of each check. `tests/test_release.py` builds a broken minimal fixture per
  check and asserts it fails. Confirm the broken fixtures match the failure modes
  you care about (missing doc, note gap, broken README link, external-URL page,
  dropped nav link, syntax error, planted secret, oversized file) and that none of
  the checks is trivially satisfiable.
- `docs_consistency` couples the CLI's `CURRENT_MILESTONE` to the latest milestone
  note. This is deliberate (it caught the 14-vs-13 drift mid-milestone) but means
  a future milestone must bump the constant and add notes together. Confirm that
  coupling is desired.
- Structural, not semantic. `release-check` does not render the site, run a real
  linter by default, or validate that the docs describe the code accurately.
  Confirm the gate's scope is understood as "consistency + cleanliness", not
  "correctness".
- README/website edits. Confirm the M14 status updates are accurate and that
  nothing now over-claims (e.g. a green `release-check` is not asserted to mean the
  test suite passed).

Technical risks
- Low. New code is a read-only checker (filesystem reads + one hygiene scan;
  subprocess only behind explicit `--with-*` flags), one CLI subcommand, and
  tests. No behavioural runtime path changed. The realistic failure modes are an
  over- or under-strict check (e.g. a link-resolution false positive) — mitigated
  by the negative tests and by the gate being advisory for lint/tests. The
  `release` import is added to `cli.py`; `release` imports only `hygiene`, so there
  is no import cycle.

Commands to verify
- `python3 scripts/08_final_checks.py`            (expect PASS, exit 0)
- `python3 scripts/08_final_checks.py --with-tests --with-lint`
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_release.py -q`
- `PYTHONPATH=src python3 -m code_agent_runtime release-check --strict`
- `PYTHONPATH=src python3 -m code_agent_runtime info`   (expect Milestone 14 status)
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
