Human review: Milestone 1 — Environment and repository hygiene

TL;DR
Adds two read-only, offline checks: an environment check (can this host build and
test the runtime without paid APIs?) and a repository hygiene scanner (does any
tracked file contain secrets or junk that should not be committed?). Both are
exposed via the CLI (`env-check`, `hygiene`) and `scripts/` wrappers, and both
are covered by CPU-only tests. No runtime/sandbox execution logic yet.

What changed
- Added `src/code_agent_runtime/environment.py` and `.../hygiene.py`.
- Added CLI subcommands `env-check` and `hygiene`; `info` now reports Milestone 1.
- Added `scripts/00_check_environment.py` and `scripts/04_check_repo_hygiene.py`.
- Added `tests/test_environment.py`, `tests/test_hygiene.py`; extended the
  scaffold-layout test to require Milestone 1 notes.
- Updated README, SECURITY_MODEL, REPRODUCIBILITY, LIMITATIONS, and the
  index/security/sandboxing website pages.

What should be checked later
- Secret-detection precision/recall. The patterns are deliberately high-precision
  (more false negatives than false positives). Confirm the generic
  `key = <value>` heuristic and its placeholder filter match your expectations,
  and decide whether entropy-based detection should be added later.
- Whether `env`/`ENV` bare directory names should be treated as virtualenvs.
  They are intentionally NOT, to avoid false positives on legitimate `env/`
  source dirs; virtualenvs are detected via `.venv`/`venv` names and
  `pyvenv.cfg` instead.
- Whether warnings (caches, node_modules, large files, result blobs) should fail
  CI by default. Today they are warnings; `--strict` promotes them to failures.
- The `--include-untracked` path is implemented but not used by the default
  scan; confirm the intended gate (tracked-only vs. including staged-untracked).

Technical risks
- Low. Both modules are read-only and offline. The scanner shells out to
  `git ls-files`; if git is missing it falls back to a filesystem walk, which on
  a very large untracked tree could be slow (it is not pruned beyond `.git`).
- Secret detection is heuristic and not a guarantee. This is documented in
  `SECURITY_MODEL.md` and `LIMITATIONS.md`.

Commands to verify
- `python3 -m pytest -q`
- `python3 scripts/00_check_environment.py`
- `python3 scripts/04_check_repo_hygiene.py`
- `PYTHONPATH=src python3 -m code_agent_runtime env-check --json`
- `PYTHONPATH=src python3 -m code_agent_runtime hygiene --root . --strict`

Human feedback
<!-- Human will fill this later. -->
