Human review: Milestone 12 — Reproducible case study

TL;DR
Expands the shipped suite from 6 to 13 small but genuine tasks across all five
plan categories (bugfix, refactor, cli_change, tests_must_pass, security), each
with a deterministic scripted solution or a sandbox probe. A new runner,
`scripts/07_case_study.py`, runs the `mock` (null) and `scripted` (solver)
baselines plus `probe` on the security tasks, with tracing on, and emits a result
CSV, Markdown/HTML reports, and one inspectable trace per run. Adds a `suite_to_csv`
exporter (wired into the `eval` CLI) and a committed, deterministic
`docs/results/case_study.csv`. Entirely offline (no model, no network, no key);
covered by `tests/test_case_study.py` (13 cases); full suite passes (370 tests).

What changed
- Fixtures: `examples/{temperature,number_theory,refactor_pricing,cli_echo,text_utils,kv_parser,secret_demo}/`.
- Tasks: 7 new under `tasks/` (bugfix×2, refactor×1, cli×1, tests×2, security×1).
- `agents/solutions.py`: `_replace_solution`/`_write_solution` factories + 7 new registrations.
- `agents/probes.py`: `_probe_secret_read` + `PROBES` registration.
- `reports/csv.py` (`suite_to_csv`) + `reports/__init__` export; `cli.py` CSV wiring
  and milestone constants bumped to 12/13.
- `scripts/07_case_study.py`; committed `docs/results/case_study.csv`.
- Tests: `tests/test_case_study.py`; extended `tests/test_scaffold_layout.py`.
- Docs/site: `docs/RESULTS.md`, `tasks/README.md`, `README.md`; website (index,
  evals, results, task-format, sandboxing, roadmap).

What should be checked later
- Task realism. The 13 tasks are intentionally small and single-step. Confirm they
  read as "meaningful small tasks" for the case study's purpose (a harness exercise
  and baseline floor), not as a capability benchmark. Each new bugfix is a single
  marked buggy token; the cli/tests/refactor tasks are full small implementations.
- The discriminating result. `scripted` passes every solvable task; `mock` fails
  the ones requiring a change. The one exception — `cli/add-shout-flag` mock passes
  because its fixture tests don't exercise the new flag — is kept deliberately as a
  coverage caveat. Confirm that exception is clearly framed everywhere (RESULTS.md,
  results.html) and is the intended teaching point, not an oversight.
- Scripted-solution robustness. `_replace_solution` reads the fixture and replaces
  a unique marked substring (e.g. `return b  # BUG: ...` → `return a`), failing
  loudly if the marker is gone. Full-structure changes use `_write_solution`
  (verbatim file content). Confirm this fixture↔solution coupling is acceptable and
  that the marked-token style is fine for the bugfix fixtures.
- The second sandbox probe. `security/secret-read-demo` attempts `.env`, `.ssh/id_rsa`,
  a `*.pem` (all denied_path), `/etc/passwd` (outside_workspace), and scp/curl
  (network_denied), with a benign `service.py` read allowed. The credential files
  are NOT present in the fixture (the policy blocks before the read). Confirm the
  expected-rule mapping is right and that relying on the policy blocking absent
  files is the intended design (it mirrors the existing unsafe-command probe).
- CSV exporter. `suite_to_csv` uses the stdlib `csv` writer (comma/quote escaping)
  and the same columns as the Markdown/HTML table; `include_runtime=False` drops the
  only machine-dependent column. Confirm the column set is what downstream tooling
  wants and that committing a deterministic CSV under `docs/results/` (not matched
  by the root `/results/` gitignore) is acceptable.
- Committed-CSV drift guard. `test_committed_canonical_csv_is_in_sync` regenerates
  the deterministic CSV from a fresh suite run and byte-compares it (skips without
  `git`, since the scoped-diff verdicts need it). Confirm re-running
  `scripts/07_case_study.py --canonical-csv docs/results/case_study.csv` is the
  documented way to refresh it.
- Generated vs committed artifacts. The runner writes JSON/CSV/MD/HTML and per-run
  traces under `results/` (gitignored); the canonical records are `docs/RESULTS.md`
  and `docs/results/case_study.csv`. Confirm this split matches the project's
  "no large generated artifacts committed" rule.
- Optional runs. The plan's optional imported Claude Code run and cost-controlled
  API run are the existing M11/M10 flows and are intentionally NOT part of this
  committed, model-free baseline. Confirm that's the intended scope for M12.

Technical risks
- Low. The new code is deterministic and dependency-free; the runtime, scoring,
  tracing, and sandbox layers are unchanged except for the additive CSV exporter
  and CLI format option. The main interpretive risk is reading the case study as a
  capability measurement — it is a harness exercise with a deterministic solver,
  and the docs say so repeatedly. Cross-milestone note: the M9 regression/flakiness
  numbers in RESULTS.md were updated to the 13-task suite (26 keys; 10 improved / 0
  regressed / 1 unchanged / 2 removed) since that demo runs over `tasks/`.

Commands to verify
- `python3 -m pytest -q`
- `python3 -m pytest tests/test_case_study.py -q`
- `python3 scripts/07_case_study.py`
- `python3 scripts/07_case_study.py --canonical-csv docs/results/case_study.csv` (then `git diff --stat docs/results/case_study.csv` — expect no change)
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --report /tmp/out.csv`
- `PYTHONPATH=src python3 -m code_agent_runtime run security/secret-read-demo --agent probe`
- `python3 scripts/04_check_repo_hygiene.py`

Human feedback
<!-- Human will fill this later. -->
