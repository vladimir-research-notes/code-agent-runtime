# Milestone 12 — Reproducible case study

## Summary

The platform pointed at a real, if small, workload. The shipped task suite is
expanded from 6 to **13 small but genuine coding tasks spanning all five plan
categories** — bugfix, refactor, cli_change, tests_must_pass, and security — each
backed by a real fixture and a deterministic scripted solution (or, for the two
security tasks, a sandbox probe). A single runner, `scripts/07_case_study.py`,
runs the two baselines the plan names — `mock` (the null baseline: change nothing)
and `scripted` (the deterministic solver) — plus `probe` on the security tasks,
**with tracing on**, and emits the result CSV the plan requires, Markdown/HTML
reports, and one inspectable trace per run.

Everything is **CPU-only, offline, and free**: no model, no network, no paid API.
The optional imported Claude Code run and cost-controlled API run the plan
mentions are the existing M11 importer and M10 LLM-adapter flows, intentionally
left out of this committed, model-free baseline.

## Plan requirements → where they live

| Requirement | Implementation |
| --- | --- |
| 10–20 meaningful small tasks | 13 tasks under `tasks/` (see `tasks/README.md`) |
| bugfixes | `bugfix/temp-convert-ratio`, `bugfix/gcd-modulo-swap` (+ the two sum-range tasks) |
| refactors | `refactor/extract-rate-constant` (+ `refactor/sum-range-diff-scope`) |
| CLI behavior changes | `cli/add-reverse-flag` (+ the two add-shout-flag tasks) |
| tests-must-pass tasks | `tests/implement-slugify`, `tests/implement-kv-parser` |
| security/sandbox tasks | `security/secret-read-demo` (+ `security/unsafe-command-demo`) |
| mock baseline | `mock` agent in the matrix (the null baseline) |
| scripted baseline | `scripted` agent + new solutions in `agents/solutions.py` |
| optional imported Claude Code run | M11 importer (`scripts/06_import_demo.py`) — documented, not in the committed baseline |
| optional cost-controlled API run | M10 LLM adapter (`run --agent llm --allow-paid`) — documented, opt-in |
| result CSV exists | `reports/csv.py` (`suite_to_csv`); committed `docs/results/case_study.csv`; generated `results/reports/case_study.csv` |
| report exists | `results/reports/case_study.{md,html}`; committed table in `docs/RESULTS.md` |
| traces are inspectable | `scripts/07_case_study.py` records one trace per run and reloads+replays one |
| website updated | `index`, `evals`, `results`, `task-format`, `sandboxing`, `roadmap` |

## Deliverables

- **Fixtures** (`examples/`): `temperature`, `number_theory`, `refactor_pricing`,
  `cli_echo`, `text_utils`, `kv_parser`, `secret_demo` — each a small module + its
  pytest file (and a README), authored so the before-state fails and the scripted
  edit makes it pass.
- **Tasks** (`tasks/`): seven new task files across `bugfix/`, `refactor/`,
  `cli/`, `tests/`, and `security/`.
- **Scripted solutions** (`agents/solutions.py`): two generic builder factories —
  `_replace_solution` (one-edit `apply_patch` from a substring replacement) and
  `_write_solution` (full-file rewrite) — plus full-rewrite constants and the
  seven new `SOLUTIONS` registrations.
- **Sandbox probe** (`agents/probes.py`): `_probe_secret_read` for
  `security/secret-read-demo` (credential exfiltration), registered in `PROBES`.
- **CSV report** (`reports/csv.py`): `suite_to_csv(suite, include_runtime=...)`,
  exported from `reports/__init__`, and wired into the CLI (`eval run`/`eval report`
  gain a `csv` format; `--report *.csv` infers it).
- **Runner** (`scripts/07_case_study.py`): discover → run matrix with tracing →
  write JSON/CSV/MD/HTML + per-run traces → reload+replay one trace; optional
  `--canonical-csv` writes the committed deterministic CSV.
- **Committed result** (`docs/results/case_study.csv`, `docs/RESULTS.md`): the
  deterministic table (no machine-dependent runtime column) and the full narrative.
- **Tests** (`tests/test_case_study.py`, 13 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 12 notes.

## Design notes / decisions

- **The result is a discrimination, not a score.** The point of running both
  baselines is that the harness and every scoring method separate a real change
  from no change: `scripted` passes every solvable task; `mock` fails the ones
  that require a change. `cli/add-shout-flag` is the deliberate exception (its
  fixture tests don't cover the new flag, so the do-nothing mock passes) — kept as
  an honest reminder that a test-command pass is bounded by test coverage.
- **Solutions are built from the fixture, not hard-coded.** `_replace_solution`
  reads the fixture, applies a substring replacement, and emits an `apply_patch`
  diff — failing loudly if the target text is gone (a guard against fixture
  drift). Full-structure changes (a new flag, a constant, an implementation) use
  `_write_solution`. This keeps the scripted agent a dumb, observation-blind
  replayer while every task-specific decision lives in one place.
- **CSV mirrors the existing reports.** `suite_to_csv` emits the same columns as
  the Markdown/HTML table via the stdlib `csv` module (so commas/quotes are
  escaped correctly). `include_runtime=False` drops the only machine-dependent
  column, giving a deterministic table safe to commit; the under-`results/` CSV
  keeps runtime as real evidence.
- **Traces prove inspectability.** The runner records a trace per run and then
  reloads one and replays it (the same Milestone 6 path as `trace show`), so
  "traces are inspectable" is demonstrated, not asserted.
- **The committed CSV cannot silently drift.** A test regenerates the deterministic
  CSV from a fresh suite run and asserts it byte-matches `docs/results/case_study.csv`
  (gated on `git`, since the scoped-diff verdicts need it).

## Honest limitations (carried into docs)

- **Small task counts make this illustrative, not statistically powerful.** It is a
  baseline floor and a harness exercise, not a benchmark or leaderboard.
- **A passing test command is evidence, not proof**, and is bounded by the
  fixture's test coverage (see `cli/add-shout-flag`). `diff_constraint` scores
  scope, not correctness; the `custom` composite combines the two.
- **The scripted solver is deterministic, not a model.** It demonstrates the
  runtime, tracing, scoring, and sandbox end to end — not agent capability. Genuine
  model runs are the opt-in M10/M11 flows.
- **The committed CSV's verdicts depend on `git`** for the scoped-diff tasks; the
  determinism test skips when `git` is absent.

## Validation

- `python3 -m pytest -q` — full CPU-only suite passes (`tests/test_case_study.py`
  added, 13 cases). No model, no network, no key.
- `python3 scripts/07_case_study.py` — 13 tasks, 26 runs (12 passed, 10 failed, 4
  not scored, 0 errored), one trace per run, replay of one trace; exit 0.
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --report out.csv`
  — the result CSV directly.
- `python3 scripts/04_check_repo_hygiene.py` — clean repository.

## Status

Complete. Next: Milestone 13 — Multi-page website polish.
