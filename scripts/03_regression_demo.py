#!/usr/bin/env python3
"""Demonstrate regression comparison and flakiness analysis (Milestone 9).

This is a *reproducible, honest* demo of the Milestone 9 tooling over the
deterministic baseline agents — no model, no paid API, CPU-only. It does two
things and writes artifacts under ``results/`` (gitignored):

1. **Flakiness.** Re-run the whole suite ``--repeats`` times and analyse it. The
   deterministic agents never flake, so the report shows **zero** flaky keys — a
   real determinism check, not a claim:

       results/raw/flakiness.json
       results/reports/flakiness.md

2. **Regression.** Compare two suite results:
   - ``mock`` (the null baseline) vs ``scripted`` (the solver) — the scripted
     "version" *improves* every solvable task, so the comparison is all improved /
     unchanged with **no regressions**:

       results/raw/eval_mock.json, results/raw/eval_scripted.json
       results/reports/regression_mock_vs_scripted.md

The deliberate asymmetry (scripted improves on mock; nothing regresses) shows the
comparator's *improved* and *unchanged* buckets on real data. The *regressed* and
*flaky* buckets are exercised by the unit tests (``tests/test_regression.py``)
with synthetic "fake agent versions", because the deterministic baseline cannot
regress against itself.

    python3 scripts/03_regression_demo.py [--dir tasks] [--repeats 3] [--no-sandbox]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime import reports as _reports  # noqa: E402
from code_agent_runtime import scoring as _scoring  # noqa: E402
from code_agent_runtime import tasks as _tasks  # noqa: E402
from code_agent_runtime.runtime import RunConfig  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=str(ROOT / "tasks"), help="Tasks directory.")
    parser.add_argument("--out", default=str(ROOT / "results"), help="Output directory.")
    parser.add_argument("--repeats", type=int, default=3, help="Repeats for flakiness (default 3).")
    parser.add_argument("--no-sandbox", action="store_true", help="Disable sandbox enforcement.")
    args = parser.parse_args(argv)

    tasks = list(_tasks.discover_tasks(args.dir, resolve_fixture=True))
    if not tasks:
        print(f"No tasks found under {args.dir}/.", file=sys.stderr)
        return 1

    out = Path(args.out)
    config = RunConfig(enforce_sandbox=not args.no_sandbox)

    # 1) Flakiness over repeated runs of the full suite.
    suites = _scoring.run_repeated(tasks, repeats=args.repeats, config=config, label=f"dir={args.dir}")
    flakiness = _scoring.analyze_flakiness(suites, label=f"dir={args.dir}")
    _scoring.write_flakiness(flakiness, out / "raw" / "flakiness.json")
    (out / "reports" / "flakiness.md").parent.mkdir(parents=True, exist_ok=True)
    (out / "reports" / "flakiness.md").write_text(
        _reports.flakiness_to_markdown(flakiness), encoding="utf-8"
    )

    # 2) Regression: mock (null baseline) vs scripted (solver).
    mock = _scoring.run_suite(tasks, agents=("mock",), config=config, label="agent=mock")
    scripted = _scoring.run_suite(tasks, agents=("scripted",), config=config, label="agent=scripted")
    # Re-key scripted onto the mock agent name so the comparator matches tasks
    # across the two "versions" rather than treating them as different keys.
    scripted_as_mock = _scoring.SuiteResult(
        records=tuple(
            _scoring.EvalRecord.from_dict({**r.to_dict(), "agent": "mock"}) for r in scripted.records
        ),
        skipped=scripted.skipped,
        label="agent=scripted",
    )
    comparison = _scoring.compare_suites(mock, scripted_as_mock)
    _scoring.write_suite_result(mock, out / "raw" / "eval_mock.json")
    _scoring.write_suite_result(scripted, out / "raw" / "eval_scripted.json")
    _scoring.write_comparison(comparison, out / "raw" / "regression_mock_vs_scripted.json")
    (out / "reports" / "regression_mock_vs_scripted.md").write_text(
        _reports.regression_to_markdown(comparison), encoding="utf-8"
    )

    print(_reports.flakiness_to_markdown(flakiness))
    print(_reports.regression_to_markdown(comparison))

    fc = flakiness.counts()
    cc = comparison.counts()
    print(
        f"\nflakiness: {args.repeats} repeats over {fc['keys']} keys — "
        f"{fc['flaky']} flaky, {fc['stable']} stable.\n"
        f"regression (mock → scripted): {cc['improved']} improved, {cc['regressed']} regressed, "
        f"{cc['unchanged']} unchanged.\n"
        f"wrote artifacts under {out}/ (gitignored).",
        file=sys.stderr,
    )
    # Honest non-zero only if the demo unexpectedly found a flake or regression.
    return 1 if flakiness.has_flakes or comparison.has_regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
