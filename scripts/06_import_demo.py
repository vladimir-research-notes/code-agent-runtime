#!/usr/bin/env python3
"""Demonstrate the Claude Code trace importer (Milestone 11).

A *reproducible, offline, no-spend* tour of the importer. It makes **zero** API
calls and needs **no** model: a deterministic scripted solution stands in for a
Claude Code run. On real artifacts it shows:

1. **Synthesize.** Generate a synthetic Claude-Code-like run for a task and write
   it as a normalised import source (the same JSON a real exported run normalises
   to).
2. **Trust mode.** Score the import against the source's *declared* evidence — the
   fast path that believes the source.
3. **Verify mode.** Reconstruct the workspace from the imported after-state and
   re-run the task's **real** test command, scoring this runtime's own
   measurement.
4. **Verification catches a lie.** A broken change carrying a forged "tests
   passed" scores ``passed`` in trust mode but ``failed`` in verify mode — the
   whole point of verification.
5. **Same trace, same tools.** The converted run is a normal trace: it round-trips
   through the schema and replays with the existing replay tooling.

Artifacts are written under ``results/`` (gitignored):

    results/raw/import_demo_source.json     (the synthetic import source)
    results/raw/import_demo.trace.json       (the converted, verified trace)
    results/reports/import_demo.md           (a Markdown report of the trace)
    results/reports/import_demo.txt          (this summary)

    python3 scripts/06_import_demo.py [--task bugfix/sum-range-off-by-one]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_agent_runtime import importers as I  # noqa: E402
from code_agent_runtime import runtime as R  # noqa: E402
from code_agent_runtime import tasks as T  # noqa: E402
from code_agent_runtime import traces as TR  # noqa: E402

_BUGGY = "    for i in range(1, n):"


def _has_git() -> bool:
    return shutil.which("git") is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task", default="bugfix/sum-range-off-by-one", help="Solvable task id.")
    parser.add_argument("--dir", default=str(ROOT / "tasks"), help="Tasks directory.")
    parser.add_argument("--out", default=str(ROOT / "results"), help="Output directory.")
    args = parser.parse_args(argv)

    task = T.find_task(args.dir, args.task, resolve_fixture=True)
    out = Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"task": task.id, "note": "offline; no API calls; no model"}

    # 1) Synthesize a Claude-Code-like import source and persist it.
    imported = I.synthesize_import(task)
    source_path = out / "raw" / "import_demo_source.json"
    I.write_import_source(imported, source_path)
    summary["synthesize"] = {
        "source_kind": imported.source_kind,
        "tool_calls": sum(1 for a in imported.actions if a.kind == "tool_call"),
        "changed_files": sorted(imported.files),
        "declared_tests_passed": (imported.tests or {}).get("passed"),
    }

    # 2) Trust mode — score the declared evidence.
    trust = I.import_to_run(imported, task, mode="trust")
    summary["trust"] = {"verified": trust.verified, "outcome": trust.result.outcome}

    # 3) Verify mode — reconstruct + re-run the real test command.
    verify = I.import_to_run(imported, task, mode="verify") if _has_git() else None
    if verify is not None:
        TR.write_trace(verify.trace, out / "raw" / "import_demo.trace.json")
        (out / "reports" / "import_demo.md").write_text(
            TR.trace_to_markdown(verify.trace), encoding="utf-8"
        )
        replay = TR.replay_trace(verify.trace)
        summary["verify"] = {
            "verified": verify.verified,
            "outcome": verify.result.outcome,
            "tests_passed": (verify.result.tests or {}).get("passed"),
            "replay_outcome": replay.outcome,
            "replay_failure_point": replay.failure_point.kind if replay.failure_point else None,
        }
    else:
        summary["verify"] = {"skipped": "git not available"}

    # 4) Verification catches a forged "tests passed" on a broken change.
    fixture = Path(T.resolve_fixture(task))
    summ = (fixture / "summation.py").read_text(encoding="utf-8")
    broken = {"summation.py": summ.replace(_BUGGY, "    for i in range(1, n - 1):")}
    diff = I.tree_diff({"summation.py": summ}, broken)
    forged = I.ImportedRun(
        schema_version=I.IMPORT_SCHEMA_VERSION,
        source_kind="before_after",
        task_id=task.id,
        agent_label="claude-code-import",
        actions=imported.actions,
        diff=diff,
        tests={"passed": True, "exit_code": 0},  # the source's (false) claim
        files=broken,
        source_meta={"note": "deliberately broken change with a forged passing claim"},
    )
    forged_trust = I.import_to_run(forged, task, mode="trust")
    forged_verify = I.import_to_run(forged, task, mode="verify") if _has_git() else None
    summary["forged_claim"] = {
        "trust_outcome": forged_trust.result.outcome,
        "verify_outcome": forged_verify.result.outcome if forged_verify else "skipped (no git)",
    }

    # --- persist + print -------------------------------------------------
    (out / "raw" / "import_demo.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    v = summary["verify"]
    lines = [
        "Milestone 11 — Claude Code trace importer (offline demo)",
        f"  task                 : {task.id}",
        f"  1. synthesize        : {summary['synthesize']['source_kind']} source, "
        f"{summary['synthesize']['tool_calls']} tool call(s), "
        f"changed {summary['synthesize']['changed_files']}",
        f"  2. trust mode        : verified={trust.verified} outcome={trust.result.outcome}",
        f"  3. verify mode       : "
        + (
            f"verified={v.get('verified')} outcome={v.get('outcome')} "
            f"(replay outcome={v.get('replay_outcome')})"
            if "outcome" in v
            else f"skipped ({v.get('skipped')})"
        ),
        f"  4. forged claim      : trust={summary['forged_claim']['trust_outcome']} "
        f"vs verify={summary['forged_claim']['verify_outcome']}",
    ]
    report = "\n".join(lines)
    (out / "reports" / "import_demo.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nwrote artifacts under {out}/ (gitignored).", file=sys.stderr)

    # Honest non-zero only if an invariant the demo asserts did not hold.
    ok = (
        trust.result.outcome == R.RunOutcome.PASSED
        and summary["synthesize"]["declared_tests_passed"] is True
        and forged_trust.result.outcome == R.RunOutcome.PASSED
    )
    if _has_git():
        ok = (
            ok
            and verify is not None
            and verify.result.outcome == R.RunOutcome.PASSED
            and verify.verified is True
            and forged_verify is not None
            and forged_verify.result.outcome == R.RunOutcome.FAILED
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
