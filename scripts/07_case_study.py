#!/usr/bin/env python3
"""Run the reproducible coding-agent case study (Milestone 12).

This is the milestone's headline artifact: a single, CPU-only, offline run of the
deterministic baseline agents over the whole shipped task suite, emitting the
result CSV / report / traces the plan calls for. No model, no network, no paid
API.

What it does, writing everything under ``results/`` (gitignored):

1. Discover every task under ``tasks/`` and run the default agent matrix
   (``mock``, ``scripted``, ``probe``) over it **with tracing on**, so each run
   leaves an inspectable trace:

       results/traces/case_study/<task>__<agent>.trace.json

2. Assemble the runs into one suite result and write it three ways — the
   machine-readable result, the CSV the plan requires, and human reports:

       results/raw/case_study.json
       results/reports/case_study.csv      (the result CSV)
       results/reports/case_study.md
       results/reports/case_study.html

3. Prove a trace is inspectable by reloading one and replaying it (the same
   Milestone 6 path as ``trace show``), printing its reconstructed timeline.

The two baselines the plan names — the ``mock`` null baseline and the ``scripted``
solver — are both in the matrix; ``probe`` exercises the sandbox on the security
tasks. The *optional* imported Claude Code run and cost-controlled API run are
demonstrated by ``scripts/06_import_demo.py`` and ``scripts/05_llm_adapter_demo.py``
respectively and are intentionally not part of this committed baseline.

The canonical, committed result table lives in ``docs/RESULTS.md`` and the
deterministic CSV in ``docs/results/case_study.csv``; pass ``--canonical-csv PATH``
to regenerate the latter (it omits the machine-dependent runtime column).

    python3 scripts/07_case_study.py [--dir tasks] [--no-sandbox] [--canonical-csv PATH]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime import reports as _reports  # noqa: E402
from code_agent_runtime import scoring as _scoring  # noqa: E402
from code_agent_runtime import tasks as _tasks  # noqa: E402
from code_agent_runtime import traces as _traces  # noqa: E402
from code_agent_runtime.runtime import RunConfig  # noqa: E402


def _trace_filename(task_id: str, agent: str) -> str:
    """A filesystem-safe trace filename for a (task, agent) run."""
    safe = task_id.replace("/", "__")
    return f"{safe}__{agent}.trace.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=str(ROOT / "tasks"), help="Tasks directory.")
    parser.add_argument("--out", default=str(ROOT / "results"), help="Output directory.")
    parser.add_argument("--no-sandbox", action="store_true", help="Disable sandbox enforcement.")
    parser.add_argument(
        "--canonical-csv",
        default=None,
        metavar="PATH",
        help="Also write a deterministic CSV (no runtime column) to PATH for committing.",
    )
    args = parser.parse_args(argv)

    tasks = list(_tasks.discover_tasks(args.dir, resolve_fixture=True))
    if not tasks:
        print(f"No tasks found under {args.dir}/.", file=sys.stderr)
        return 1

    out = Path(args.out)
    trace_dir = out / "traces" / "case_study"
    trace_dir.mkdir(parents=True, exist_ok=True)
    config = RunConfig(enforce_sandbox=not args.no_sandbox)

    # 1) Run the full matrix with tracing on; record one trace per run.
    records: list[_scoring.EvalRecord] = []
    skipped: list[dict[str, str]] = []
    one_trace_path: Path | None = None

    for task in tasks:
        for agent_name in _scoring.DEFAULT_AGENTS:
            agent = _scoring.build_agent(agent_name, task)
            if agent is None:
                skipped.append({"task_id": task.id, "agent": agent_name})
                continue
            start = time.perf_counter()
            result, trace = _traces.record_run(task, agent, config=config)
            elapsed = time.perf_counter() - start
            trace_path = trace_dir / _trace_filename(task.id, agent_name)
            _traces.write_trace(trace, trace_path)
            records.append(
                _scoring.EvalRecord.from_result(
                    result, runtime_seconds=elapsed, trace_path=str(trace_path)
                )
            )
            # Keep one scripted-pass trace handy to demonstrate replay below.
            if one_trace_path is None and agent_name == "scripted" and result.passed:
                one_trace_path = trace_path

    suite = _scoring.SuiteResult(
        records=tuple(records), skipped=tuple(skipped), label=f"case-study dir={args.dir}"
    )

    # 2) Persist the suite result, the CSV, and the human reports.
    raw = _scoring.write_suite_result(suite, out / "raw" / "case_study.json")
    reports_dir = out / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = reports_dir / "case_study.csv"
    md_path = reports_dir / "case_study.md"
    html_path = reports_dir / "case_study.html"
    csv_path.write_text(_reports.suite_to_csv(suite), encoding="utf-8")
    md_path.write_text(_reports.suite_to_markdown(suite, title="Case study results"), encoding="utf-8")
    html_path.write_text(_reports.suite_to_html(suite, title="Case study results"), encoding="utf-8")

    if args.canonical_csv:
        canonical = Path(args.canonical_csv)
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(_reports.suite_to_csv(suite, include_runtime=False), encoding="utf-8")

    # 3) Prove a trace is inspectable: reload one and replay it.
    replay_line = "no scripted-pass trace to replay"
    if one_trace_path is not None:
        reloaded = _traces.load_trace(one_trace_path)
        replayed = _traces.replay_trace(reloaded)
        replay_line = (
            f"replayed {one_trace_path.name}: {len(replayed.tool_calls)} tool call(s), "
            f"outcome={replayed.outcome}"
        )

    print(_reports.suite_to_markdown(suite, title="Case study results"))

    totals = suite.totals()
    categories = Counter(t.metadata.get("category", "uncategorised") for t in tasks)
    cat_str = ", ".join(f"{k}={v}" for k, v in sorted(categories.items()))
    print(
        f"\ncase study: {len(tasks)} task(s) across categories [{cat_str}]\n"
        f"{suite.total} run(s): {totals['passed']} passed, {totals['failed']} failed, "
        f"{totals['not_scored']} not scored, {totals['error']} errored; "
        f"{len(skipped)} pair(s) skipped.\n"
        f"traces: {len(records)} written under {trace_dir}/ ({replay_line}).\n"
        f"wrote: {raw}, {csv_path}, {md_path}, {html_path}"
        + (f", {args.canonical_csv}" if args.canonical_csv else "")
        + " (under results/, gitignored).",
        file=sys.stderr,
    )
    # Honest non-zero only if a run errored at the harness level.
    return 2 if totals["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
