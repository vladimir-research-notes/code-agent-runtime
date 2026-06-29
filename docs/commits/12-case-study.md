# Commit note — Milestone 12

**Commit message:** `Add reproducible coding-agent case study`

## What this commit adds

- **Fixtures** (`examples/`): `temperature/`, `number_theory/`,
  `refactor_pricing/`, `cli_echo/`, `text_utils/`, `kv_parser/`, `secret_demo/` —
  each a small module, its pytest file, and a README. The before-state fails; the
  scripted edit makes it pass (the security fixture is benign — its probe is
  blocked before any read).
- **Tasks** (`tasks/`): `bugfix/temp-convert-ratio`, `bugfix/gcd-modulo-swap`,
  `refactor/extract-rate-constant`, `cli/add-reverse-flag`,
  `tests/implement-slugify`, `tests/implement-kv-parser`,
  `security/secret-read-demo` — bringing the suite to 13 tasks across all five
  categories.
- `agents/solutions.py` — `_replace_solution` (one-edit `apply_patch`) and
  `_write_solution` (full rewrite) builder factories, full-rewrite constants, and
  the seven new `SOLUTIONS` registrations.
- `agents/probes.py` — `_probe_secret_read` (credential-exfiltration probe) and
  its `PROBES` registration for `security/secret-read-demo`.
- `reports/csv.py` — `suite_to_csv(suite, include_runtime=...)`; exported from
  `reports/__init__`.
- `cli.py` — `csv` added to `eval run`/`eval report` `--format`; `_render_suite`
  and `_fmt_for_path` handle CSV (`--report *.csv` inferred); milestone constants
  bumped to 12/13.
- `scripts/07_case_study.py` — the case-study runner (matrix with tracing → JSON /
  CSV / Markdown / HTML / per-run traces → reload+replay one; `--canonical-csv`).
- `docs/results/case_study.csv` — the committed, deterministic result table.
- Tests: `tests/test_case_study.py` (13 cases); `tests/test_scaffold_layout.py`
  extended for the Milestone 12 notes.
- Docs/site: `docs/RESULTS.md`, `tasks/README.md`, `README.md`; website `index`,
  `evals`, `results`, `task-format`, `sandboxing`, `roadmap`; Milestone 12
  milestone/commit/review notes.

## Excluded (per operating principles)

No secrets, API keys, virtualenvs, caches, `node_modules`, weights, or large
artifacts. **No model and no network** anywhere: the case study runs deterministic
mock/scripted/probe agents on CPU-only fixtures. The credential files the secret
probe targets (`.env`, `.ssh/id_rsa`, `*.pem`) are deliberately **absent** — the
policy blocks the read before the tool runs, so nothing secret is committed.
Generated `results/`/`traces/` artifacts stay gitignored; the canonical records are
`docs/RESULTS.md` and the small deterministic `docs/results/case_study.csv`
(`docs/results/` is not matched by the root-anchored `/results/` ignore).

## Honesty notes

The case study measures the harness, not a model. The headline — `scripted` passes
every solvable task, `mock` fails the ones requiring a change — confirms the
runtime and every scoring method discriminate a real change from no change. The
one deliberate non-discriminating case (`cli/add-shout-flag` mock passes) is kept
as an honest coverage caveat. Small task counts make this illustrative, not a
benchmark; a test-command pass is evidence, not proof; `diff_constraint` scores
scope, not correctness. The committed CSV is regenerated and byte-compared by a
test so it cannot silently drift (gated on `git`).

## Verification at commit time

- `python3 -m pytest -q` passes (`tests/test_case_study.py` added; 13 cases). No
  model, key, or network. Scoped-diff assertions skip when `git` is absent.
- `python3 scripts/07_case_study.py` — 13 tasks, 26 runs (12 passed, 10 failed, 4
  not scored, 0 errored), 26 traces, one replay; exit 0.
- `PYTHONPATH=src python3 -m code_agent_runtime eval run --dir tasks --report out.csv`
  writes the result CSV; `eval report ... --format csv` re-renders it.
- `python3 scripts/04_check_repo_hygiene.py` reports a clean repository.
