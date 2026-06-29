"""Command-line interface for Code Agent Runtime.

The CLI is intentionally minimal at this stage. It exposes version/status
commands, the Milestone 1 operational checks (``env-check``, ``hygiene``), the
Milestone 2 task tools (``tasks list`` / ``tasks show``), the Milestone 3 tool
registry (``tools list`` / ``tools show``), the Milestone 4 runtime (``run``)
with optional Milestone 5 trace recording (``run --trace``), the Milestone 6
trace inspection/replay tooling (``trace show`` / ``trace report``), the
Milestone 7 sandbox controls (enforced by default on ``run``, with
``run --no-sandbox`` to disable and ``run --agent probe`` to exercise them), the
Milestone 8 scoring/eval suite (``eval run`` runs a task×agent matrix and
emits a result file and a Markdown/HTML report; ``eval report`` re-renders a saved
result file), and the Milestone 9 regression/flakiness tooling (``eval compare``
diffs two result files into improved/regressed/unchanged/flaky buckets; ``eval
rerun`` re-runs the matrix N times and reports flaky keys), and the Milestone 10
optional cost-controlled LLM adapter (``run --agent llm`` drives a task through a
model-backed agent; offline by default via a deterministic fake client, with
``--dry-run`` to preview the request and its cost, and ``--allow-paid`` to opt
into a real, budget-guarded Claude API run). Later milestones add a Claude Code
trace importer (see ``docs/PLAN.md``).
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path

from . import PROJECT_NAME, PROJECT_SUMMARY, __version__
from . import agents as _agents
from . import environment as _environment
from . import hygiene as _hygiene
from . import reports as _reports
from . import runtime as _runtime
from . import scoring as _scoring
from . import tasks as _tasks
from . import tools as _tools
from . import traces as _traces

# The milestone the runtime currently implements. Kept here so ``info`` can
# report honest project status without scanning the filesystem.
CURRENT_MILESTONE = "Milestone 10 — Optional cost-controlled LLM adapter"
NEXT_MILESTONE = "Milestone 11 — Claude Code trace importer"

#: Default directory the ``tasks`` subcommands scan.
DEFAULT_TASKS_DIR = "tasks"


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="code-agent-runtime",
        description=PROJECT_SUMMARY,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "This is a research/engineering scaffold. Most subcommands are "
            "added in later milestones; run `code-agent-runtime info` for "
            "current status."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    p_version = subparsers.add_parser(
        "version",
        help="Print the runtime version and exit.",
    )
    p_version.set_defaults(func=_cmd_version)

    p_info = subparsers.add_parser(
        "info",
        help="Print project name, summary, and current milestone status.",
    )
    p_info.set_defaults(func=_cmd_info)

    p_env = subparsers.add_parser(
        "env-check",
        help="Check the host satisfies the runtime's CPU-only, no-paid-API requirements.",
    )
    p_env.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    p_env.set_defaults(func=_cmd_env_check)

    p_hyg = subparsers.add_parser(
        "hygiene",
        help="Scan tracked files for secrets, junk, and large/binary artifacts.",
    )
    p_hyg.add_argument("--root", default=".", help="Repository root to scan (default: cwd).")
    p_hyg.add_argument(
        "--max-bytes",
        type=int,
        default=_hygiene.DEFAULT_MAX_BYTES,
        help="Large-file threshold in bytes.",
    )
    p_hyg.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also scan untracked, non-gitignored files.",
    )
    p_hyg.add_argument("--strict", action="store_true", help="Treat warnings as failures too.")
    p_hyg.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    p_hyg.set_defaults(func=_cmd_hygiene)

    _add_tasks_parser(subparsers)
    _add_tools_parser(subparsers)
    _add_run_parser(subparsers)
    _add_trace_parser(subparsers)
    _add_eval_parser(subparsers)

    return parser


def _add_tasks_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``tasks`` command group (``list`` / ``show``)."""
    p_tasks = subparsers.add_parser(
        "tasks",
        help="List and inspect versioned task definitions.",
    )
    # Invoking `tasks` with no action prints this parser's help.
    p_tasks.set_defaults(func=_make_help_printer(p_tasks))
    actions = p_tasks.add_subparsers(dest="tasks_command", metavar="<action>")

    p_list = actions.add_parser("list", help="List discovered tasks.")
    p_list.add_argument(
        "--dir", default=DEFAULT_TASKS_DIR, help="Directory to scan (default: tasks/)."
    )
    p_list.add_argument("--json", action="store_true", help="Emit the listing as JSON.")
    p_list.set_defaults(func=_cmd_tasks_list)

    p_show = actions.add_parser("show", help="Show one task by id or file path.")
    p_show.add_argument("ident", help="Task id (e.g. bugfix/sum-range-off-by-one) or path.")
    p_show.add_argument(
        "--dir", default=DEFAULT_TASKS_DIR, help="Directory to search by id (default: tasks/)."
    )
    p_show.add_argument("--json", action="store_true", help="Emit the task as JSON.")
    p_show.set_defaults(func=_cmd_tasks_show)


def _add_tools_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``tools`` command group (``list`` / ``show``)."""
    p_tools = subparsers.add_parser(
        "tools",
        help="List and inspect the registered structured tools.",
    )
    p_tools.set_defaults(func=_make_help_printer(p_tools))
    actions = p_tools.add_subparsers(dest="tools_command", metavar="<action>")

    p_list = actions.add_parser("list", help="List registered tools.")
    p_list.add_argument("--json", action="store_true", help="Emit the listing as JSON.")
    p_list.set_defaults(func=_cmd_tools_list)

    p_show = actions.add_parser("show", help="Show one tool's spec (parameters).")
    p_show.add_argument("name", help="Tool name (e.g. read_file).")
    p_show.add_argument("--json", action="store_true", help="Emit the spec as JSON.")
    p_show.set_defaults(func=_cmd_tools_show)


def _add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``run`` command: drive a task with a mock or scripted agent."""
    p_run = subparsers.add_parser(
        "run",
        help="Run a task with a deterministic mock or scripted agent.",
    )
    p_run.add_argument("ident", help="Task id (e.g. bugfix/sum-range-off-by-one) or path.")
    p_run.add_argument(
        "--dir", default=DEFAULT_TASKS_DIR, help="Directory to search by id (default: tasks/)."
    )
    p_run.add_argument(
        "--agent",
        choices=["mock", "scripted", "probe", "llm"],
        default="scripted",
        help=(
            "Which agent to run (default: scripted). 'probe' replays an adversarial "
            "sandbox probe (only for tasks that define one). 'llm' runs the optional "
            "Milestone 10 model-backed agent — offline by default (a deterministic "
            "fake client that solves tasks with a built-in solution), or against the "
            "real Claude API with --allow-paid. See the 'LLM adapter' options."
        ),
    )
    p_run.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable sandbox-policy enforcement (use pure allowed_tools gating).",
    )
    p_run.add_argument(
        "--max-steps",
        type=int,
        default=_runtime.RunConfig().max_steps,
        help="Hard cap on agent steps (default: %(default)s).",
    )
    p_run.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip running the task's test command after the agent loop.",
    )
    p_run.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the ephemeral workspace on disk and print its path.",
    )
    p_run.add_argument(
        "--trace",
        nargs="?",
        const="traces",
        default=None,
        metavar="PATH",
        help=(
            "Record a structured trace of the run. PATH ending in .json is the "
            "output file; any other PATH (default: traces/) is a directory the "
            "trace is written into as <trace_id>.trace.json."
        ),
    )
    p_run.add_argument("--json", action="store_true", help="Emit the run result as JSON.")

    llm = p_run.add_argument_group(
        "LLM adapter (Milestone 10)",
        "Options for --agent llm. Disabled by default; offline unless --allow-paid.",
    )
    llm.add_argument(
        "--llm-model",
        default=_agents.DEFAULT_MODEL,
        metavar="MODEL",
        help="Model id for the LLM agent (default: %(default)s, the cheapest priced model).",
    )
    llm.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        metavar="USD",
        help=(
            "Hard budget ceiling in USD. Required with --allow-paid; the guard "
            "refuses any call whose worst case would exceed it. Offline runs default "
            "to a generous internal budget."
        ),
    )
    llm.add_argument(
        "--max-output-tokens",
        type=int,
        default=1024,
        metavar="N",
        help="max_tokens per model call (also the worst-case output for the cost guard).",
    )
    llm.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the first request and its worst-case cost; make NO calls and spend nothing.",
    )
    llm.add_argument(
        "--allow-paid",
        action="store_true",
        help="Opt into a real, paid Claude API run (needs ANTHROPIC_API_KEY and --max-cost-usd).",
    )
    llm.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        help="Persist/reuse LLM responses under PATH (default: in-memory, per-process).",
    )
    llm.add_argument(
        "--no-cache", action="store_true", help="Disable the response cache entirely."
    )
    llm.add_argument(
        "--no-redact-transcript",
        action="store_true",
        help="Do not redact credential-shaped text from the stored/sent transcript (NOT advised).",
    )
    llm.add_argument(
        "--show-transcript",
        action="store_true",
        help="Print the (redacted) model transcript after the run.",
    )
    p_run.set_defaults(func=_cmd_run)


def _add_trace_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``trace`` command group (``show`` / ``report``).

    These reconstruct a run from a stored trace *without re-executing it* — the
    Milestone 6 replay/debugging tooling.
    """
    p_trace = subparsers.add_parser(
        "trace",
        help="Inspect and replay recorded run traces (timeline, diff, tests, failure point).",
    )
    p_trace.set_defaults(func=_make_help_printer(p_trace))
    actions = p_trace.add_subparsers(dest="trace_command", metavar="<action>")

    p_show = actions.add_parser(
        "show",
        help="Reconstruct and summarise a trace: timeline, tool calls, diff, tests, failure point.",
    )
    p_show.add_argument("path", help="Path to a recorded trace (a .trace.json file).")
    p_show.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured reconstruction (ReplayedRun) as JSON instead of text.",
    )
    p_show.set_defaults(func=_cmd_trace_show)

    p_report = actions.add_parser(
        "report",
        help="Generate a Markdown report from a trace.",
    )
    p_report.add_argument("path", help="Path to a recorded trace (a .trace.json file).")
    p_report.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write the Markdown report to PATH instead of stdout.",
    )
    p_report.set_defaults(func=_cmd_trace_report)


def _add_eval_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``eval`` command group (``run`` / ``report``) — Milestone 8.

    ``eval run`` runs a task×agent matrix, scores each run, and writes a result
    file and/or a Markdown/HTML report. ``eval report`` re-renders a saved result
    file without re-running anything.
    """
    p_eval = subparsers.add_parser(
        "eval",
        help="Run a scoring/eval suite and generate Markdown/HTML reports.",
    )
    p_eval.set_defaults(func=_make_help_printer(p_eval))
    actions = p_eval.add_subparsers(dest="eval_command", metavar="<action>")

    p_run = actions.add_parser("run", help="Run a suite over tasks and agents.")
    p_run.add_argument(
        "idents",
        nargs="*",
        help="Task ids/paths to include (default: every task under --dir).",
    )
    p_run.add_argument(
        "--dir", default=DEFAULT_TASKS_DIR, help="Directory to scan (default: tasks/)."
    )
    p_run.add_argument(
        "--agent",
        choices=["mock", "scripted", "probe", "all"],
        default="all",
        help="Agent(s) to run (default: all — mock, scripted where solvable, probe where defined).",
    )
    p_run.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable sandbox-policy enforcement for the runs.",
    )
    p_run.add_argument(
        "--max-steps",
        type=int,
        default=_runtime.RunConfig().max_steps,
        help="Hard cap on agent steps per run (default: %(default)s).",
    )
    p_run.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip running each task's test command.",
    )
    p_run.add_argument(
        "--out", default=None, metavar="PATH", help="Write the suite result as JSON to PATH."
    )
    p_run.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help="Write a report to PATH (format inferred: .html → HTML, else Markdown).",
    )
    p_run.add_argument(
        "--format",
        choices=["markdown", "html"],
        default="markdown",
        help="Format for the report printed to stdout (default: markdown).",
    )
    p_run.add_argument(
        "--json",
        action="store_true",
        help="Print the suite result as JSON to stdout instead of a report.",
    )
    p_run.set_defaults(func=_cmd_eval_run)

    p_report = actions.add_parser("report", help="Re-render a saved suite result file.")
    p_report.add_argument("path", help="Path to a suite result JSON (from `eval run --out`).")
    p_report.add_argument(
        "--format",
        choices=["markdown", "html"],
        default="markdown",
        help="Report format (default: markdown).",
    )
    p_report.add_argument(
        "--out", default=None, metavar="PATH", help="Write the report to PATH instead of stdout."
    )
    p_report.set_defaults(func=_cmd_eval_report)

    p_compare = actions.add_parser(
        "compare",
        help="Diff two suite result files into improved/regressed/unchanged/flaky buckets.",
    )
    p_compare.add_argument("baseline", help="Path to the baseline suite result JSON.")
    p_compare.add_argument("candidate", help="Path to the candidate suite result JSON.")
    p_compare.add_argument(
        "--out", default=None, metavar="PATH", help="Write the comparison as JSON to PATH."
    )
    p_compare.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help="Write the Markdown comparison report to PATH.",
    )
    p_compare.add_argument(
        "--json",
        action="store_true",
        help="Print the comparison as JSON to stdout instead of a Markdown report.",
    )
    p_compare.set_defaults(func=_cmd_eval_compare)

    p_rerun = actions.add_parser(
        "rerun",
        help="Re-run the matrix N times and report flaky (non-deterministic) keys.",
    )
    p_rerun.add_argument(
        "idents",
        nargs="*",
        help="Task ids/paths to include (default: every task under --dir).",
    )
    p_rerun.add_argument(
        "--dir", default=DEFAULT_TASKS_DIR, help="Directory to scan (default: tasks/)."
    )
    p_rerun.add_argument(
        "--agent",
        choices=["mock", "scripted", "probe", "all"],
        default="all",
        help="Agent(s) to run (default: all).",
    )
    p_rerun.add_argument(
        "--repeats", type=int, default=3, help="How many times to re-run the matrix (default: 3)."
    )
    p_rerun.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable sandbox-policy enforcement for the runs.",
    )
    p_rerun.add_argument(
        "--max-steps",
        type=int,
        default=_runtime.RunConfig().max_steps,
        help="Hard cap on agent steps per run (default: %(default)s).",
    )
    p_rerun.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip running each task's test command.",
    )
    p_rerun.add_argument(
        "--out", default=None, metavar="PATH", help="Write the flakiness report as JSON to PATH."
    )
    p_rerun.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help="Write the Markdown flakiness report to PATH.",
    )
    p_rerun.add_argument(
        "--json",
        action="store_true",
        help="Print the flakiness report as JSON to stdout instead of Markdown.",
    )
    p_rerun.set_defaults(func=_cmd_eval_rerun)


def _make_help_printer(parser: argparse.ArgumentParser):
    def _printer(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 0

    return _printer


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _cmd_info(_args: argparse.Namespace) -> int:
    print(f"{PROJECT_NAME} {__version__}")
    print(PROJECT_SUMMARY)
    print()
    print(f"Status : {CURRENT_MILESTONE}")
    print(f"Next   : {NEXT_MILESTONE}")
    print()
    print("Docs   : see docs/PLAN.md and the site/ website.")
    return 0


def _cmd_env_check(args: argparse.Namespace) -> int:
    return _environment.main(["--json"] if args.json else [])


def _cmd_hygiene(args: argparse.Namespace) -> int:
    forwarded = ["--root", args.root, "--max-bytes", str(args.max_bytes)]
    if args.include_untracked:
        forwarded.append("--include-untracked")
    if args.strict:
        forwarded.append("--strict")
    if args.json:
        forwarded.append("--json")
    return _hygiene.main(forwarded)


def _task_summary(task: _tasks.Task) -> dict:
    """Compact, JSON-friendly summary used by ``tasks list``."""
    return {
        "id": task.id,
        "title": task.title,
        "scoring_method": task.scoring_method,
        "allowed_tools": list(task.allowed_tools),
        "fixture": task.fixture,
        "fixture_exists": _tasks.fixture_exists(task),
        "source_path": task.source_path,
    }


def _cmd_tasks_list(args: argparse.Namespace) -> int:
    files = _tasks.discover_task_files(args.dir)
    loaded: list[_tasks.Task] = []
    errors: list[tuple[str, _tasks.TaskValidationError]] = []
    for path in files:
        try:
            # Validate the schema but do not hard-fail on a missing fixture; the
            # listing reports fixture presence as a column instead.
            loaded.append(_tasks.load_task(path, resolve_fixture=False))
        except _tasks.TaskValidationError as exc:
            errors.append((str(path), exc))

    if args.json:
        payload = {
            "dir": str(args.dir),
            "count": len(loaded),
            "tasks": [_task_summary(t) for t in loaded],
            "errors": [{"path": p, "problems": e.problems} for p, e in errors],
        }
        print(json.dumps(payload, indent=2))
        return 1 if errors else 0

    if not files:
        print(f"No task files (*.task.json/.yaml) found under {args.dir}/.")
        return 0
    print(f"Tasks under {args.dir}/ ({len(loaded)} valid, {len(errors)} invalid)\n")
    width = max((len(t.id) for t in loaded), default=0)
    for task in loaded:
        fixture_state = "ok" if _tasks.fixture_exists(task) else "MISSING"
        tools = f"{len(task.allowed_tools)} tool(s)"
        print(
            f"  {task.id:<{width}}  {task.scoring_method:<14} {tools:<10} "
            f"fixture: {fixture_state:<7} {task.source_path}"
        )
    for path, exc in errors:
        print(f"\n  [invalid] {path}")
        for problem in exc.problems:
            print(f"            - {problem}")
    return 1 if errors else 0


def _cmd_tasks_show(args: argparse.Namespace) -> int:
    try:
        task = _tasks.find_task(args.dir, args.ident, resolve_fixture=False)
    except _tasks.TaskValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(task.to_dict(), indent=2))
    else:
        print(_format_task(task))
    return 0


def _format_task(task: _tasks.Task) -> str:
    resolved = _tasks.resolve_fixture(task)
    exists = "exists" if resolved.exists() else "MISSING"
    limits = task.resource_limits.to_dict()
    limits_str = ", ".join(f"{k}={v}" for k, v in limits.items() if v is not None) or "(defaults)"
    meta_str = ", ".join(f"{k}={v}" for k, v in task.metadata.items()) or "(none)"
    tools_str = ", ".join(task.allowed_tools) or "(none)"
    lines = [
        f"Task: {task.id}",
        f"  title         : {task.title}",
        f"  version       : {task.version}",
        f"  scoring       : {task.scoring_method}",
        f"  test command  : {task.test_command_str or '(none)'}",
        f"  fixture       : {task.fixture} -> {resolved} ({exists})",
        f"  allowed tools : {tools_str}",
        f"  timeout       : {task.timeout_seconds}s",
        f"  limits        : {limits_str}",
        f"  metadata      : {meta_str}",
        f"  source        : {task.source_path}",
        "  prompt        :",
    ]
    lines += [f"    {line}" for line in textwrap.wrap(task.prompt, width=80)]
    return "\n".join(lines)


def _cmd_tools_list(args: argparse.Namespace) -> int:
    registry = _tools.build_registry()
    specs = registry.specs()
    if args.json:
        print(json.dumps({"count": len(specs), "tools": [s.to_dict() for s in specs]}, indent=2))
        return 0
    print(f"Registered tools ({len(specs)}):\n")
    width = max((len(s.name) for s in specs), default=0)
    for spec in specs:
        print(f"  {spec.name:<{width}}  [{spec.category:<5}] {spec.summary}")
    return 0


def _cmd_tools_show(args: argparse.Namespace) -> int:
    registry = _tools.build_registry()
    try:
        spec = registry.get(args.name).spec
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(spec.to_dict(), indent=2))
        return 0
    print(_format_tool_spec(spec))
    return 0


def _format_tool_spec(spec: _tools.ToolSpec) -> str:
    lines = [
        f"Tool: {spec.name}",
        f"  category : {spec.category}",
        f"  summary  : {spec.summary}",
        "  params   :" if spec.params else "  params   : (none)",
    ]
    for param in spec.params:
        req = "required" if param.required else "optional"
        lines.append(f"    - {param.name} ({param.type}, {req}): {param.description}")
    return "\n".join(lines)


def _cmd_run(args: argparse.Namespace) -> int:
    # Stage 1 — load and validate the task (fixture must exist to run it).
    try:
        task = _tasks.find_task(args.dir, args.ident, resolve_fixture=True)
    except _tasks.TaskValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.agent == "llm":
        return _run_llm(args, task)

    if args.agent == "mock":
        agent: _agents.Agent = _agents.MockAgent()
    elif args.agent == "probe":
        try:
            agent = _agents.build_unsafe_probe_agent(task)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        try:
            agent = _agents.build_scripted_agent(task)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    config = _runtime.RunConfig(
        max_steps=args.max_steps,
        run_tests=not args.no_tests,
        keep_workspace=args.keep_workspace,
        enforce_sandbox=not args.no_sandbox,
    )

    trace = None
    if args.trace is not None:
        result, trace = _traces.record_run(task, agent, config=config)
    else:
        result = _runtime.run_task(task, agent, config=config)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_runtime.format_run_report(result))

    if trace is not None:
        written = _traces.write_trace(trace, args.trace)
        # Trace path to stderr so it does not pollute --json stdout.
        print(f"trace written: {written} ({len(trace.events)} events)", file=sys.stderr)

    # Exit code mirrors the verdict: 0 passed/not-scored, 1 failed, 2 errored.
    if result.outcome == _runtime.RunOutcome.ERROR:
        return 2
    if result.outcome == _runtime.RunOutcome.FAILED:
        return 1
    return 0


def _run_llm(args: argparse.Namespace, task: _tasks.Task) -> int:
    """Run the optional Milestone 10 LLM agent over ``task``.

    Three paths share one cost guard:

    - ``--dry-run``    — preview the first request and its worst-case cost; make
      **no** calls and spend nothing.
    - ``--allow-paid`` — a real, budget-guarded Claude API run (needs
      ``ANTHROPIC_API_KEY`` and a positive ``--max-cost-usd``).
    - default          — an **offline** run driven by a deterministic fake client
      that replays the task's built-in solution through the model wire format, so
      the whole path is exercised with no API key and no spend.
    """
    config = _agents.LLMAgentConfig(model=args.llm_model, max_tokens=args.max_output_tokens)

    # --- dry run: preview only, never construct a client or spend ----------
    if args.dry_run:
        budget = (
            _agents.BudgetGuard(max_cost_usd=args.max_cost_usd)
            if args.max_cost_usd is not None
            else None
        )
        plan = _agents.dry_run_plan(task, config=config, budget=budget)
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(_format_dry_run(plan))
        return 0

    cache = None if args.no_cache else _agents.ResponseCache(args.cache_dir)
    redact = not args.no_redact_transcript

    if args.allow_paid:
        if args.max_cost_usd is None or args.max_cost_usd <= 0:
            print(
                "--allow-paid requires a positive --max-cost-usd (the hard budget ceiling).",
                file=sys.stderr,
            )
            return 2
        budget = _agents.BudgetGuard(max_cost_usd=args.max_cost_usd)
        try:
            client = _agents.build_claude_client(args.llm_model)
        except _agents.LLMClientError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        agent: _agents.Agent = _agents.build_llm_agent(
            task, client, budget=budget, config=config, cache=cache, redact_transcript=redact
        )
    else:
        budget = (
            _agents.BudgetGuard(max_cost_usd=args.max_cost_usd)
            if args.max_cost_usd is not None
            else None
        )
        try:
            agent = _agents.build_fake_llm_agent(
                task, budget=budget, config=config, cache=cache, redact_transcript=redact
            )
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    run_config = _runtime.RunConfig(
        max_steps=args.max_steps,
        run_tests=not args.no_tests,
        keep_workspace=args.keep_workspace,
        enforce_sandbox=not args.no_sandbox,
    )

    trace = None
    if args.trace is not None:
        result, trace = _traces.record_run(task, agent, config=run_config)
    else:
        result = _runtime.run_task(task, agent, config=run_config)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(_runtime.format_run_report(result))

    if trace is not None:
        written = _traces.write_trace(trace, args.trace)
        print(f"trace written: {written} ({len(trace.events)} events)", file=sys.stderr)

    if args.show_transcript:
        print("\n--- transcript (redacted) ---", file=sys.stderr)
        for msg in agent.transcript():
            print(f"[{msg['role']}] {msg['content']}", file=sys.stderr)

    # Usage to stderr so it never pollutes --json stdout.
    usage = agent.usage()
    b = usage["budget"]
    print(
        f"llm usage: client={usage['client']} model={usage['model']} "
        f"calls={b['calls']} refusals={b['refusals']} "
        f"spent=${b['spent_usd']:.6f} of ${b['max_cost_usd']:.4f} "
        f"tokens(in/out)={b['input_tokens']}/{b['output_tokens']} "
        f"redactions={usage['transcript_redactions']}",
        file=sys.stderr,
    )

    if result.outcome == _runtime.RunOutcome.ERROR:
        return 2
    if result.outcome == _runtime.RunOutcome.FAILED:
        return 1
    return 0


def _format_dry_run(plan: dict) -> str:
    """Render a :func:`code_agent_runtime.agents.dry_run_plan` result as text."""
    b = plan["budget"]
    lines = [
        "DRY RUN — no API calls were made and nothing was spent.",
        f"  task          : {plan['task_id']}",
        f"  model         : {plan['model']}",
        f"  max_tokens    : {plan['max_tokens']}",
        f"  est. input    : ~{plan['estimated_input_tokens']} tokens",
    ]
    if plan["priced"]:
        lines.append(f"  worst-case 1st call : ${plan['worst_case_first_call_usd']:.6f}")
    else:
        lines.append(f"  worst-case 1st call : UNPRICED — {plan.get('price_note', '')}")
    lines.append(f"  budget ceiling      : ${b['max_cost_usd']:.4f}")
    lines.append("")
    lines.append("System prompt:")
    lines += [f"  {line}" for line in plan["system_prompt"].splitlines()]
    lines.append("")
    lines.append("First user message:")
    lines += [f"  {line}" for line in plan["first_user_message"].splitlines()]
    return "\n".join(lines)


def _load_trace_or_report(path: str) -> _traces.Trace | None:
    """Load a trace for an inspection command, or print an error and return None.

    A trace inspector should fail loudly on a missing or malformed file rather
    than crash, so the loader's exceptions are caught and turned into a readable
    stderr message; the caller maps ``None`` to exit code 1.
    """
    try:
        return _traces.load_trace(path)
    except (OSError, ValueError, KeyError) as exc:
        print(f"could not load trace {path!r}: {exc}", file=sys.stderr)
        return None


def _cmd_trace_show(args: argparse.Namespace) -> int:
    trace = _load_trace_or_report(args.path)
    if trace is None:
        return 1
    if args.json:
        print(json.dumps(_traces.replay_trace(trace).to_dict(), indent=2))
    else:
        print(_traces.summarize_trace(trace))
    return 0


def _cmd_trace_report(args: argparse.Namespace) -> int:
    trace = _load_trace_or_report(args.path)
    if trace is None:
        return 1
    markdown = _traces.trace_to_markdown(trace)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        # Path to stderr so a redirected stdout stays the report (if any).
        print(f"report written: {out}", file=sys.stderr)
    else:
        print(markdown)
    return 0


def _render_suite(suite: _scoring.SuiteResult, fmt: str) -> str:
    """Render a suite result as Markdown or HTML."""
    if fmt == "html":
        return _reports.suite_to_html(suite)
    return _reports.suite_to_markdown(suite)


def _fmt_for_path(path: str) -> str:
    return "html" if path.lower().endswith((".html", ".htm")) else "markdown"


def _select_eval_tasks(args: argparse.Namespace) -> list[_tasks.Task] | None:
    """Resolve the tasks for an eval run, or print an error and return ``None``."""
    try:
        if args.idents:
            return [
                _tasks.find_task(args.dir, ident, resolve_fixture=True) for ident in args.idents
            ]
        return list(_tasks.discover_tasks(args.dir, resolve_fixture=True))
    except _tasks.TaskValidationError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _cmd_eval_run(args: argparse.Namespace) -> int:
    tasks = _select_eval_tasks(args)
    if tasks is None:
        return 1
    if not tasks:
        print(f"No tasks found under {args.dir}/.", file=sys.stderr)
        return 1

    agents = (
        _scoring.DEFAULT_AGENTS if args.agent == "all" else (args.agent,)
    )
    config = _runtime.RunConfig(
        max_steps=args.max_steps,
        run_tests=not args.no_tests,
        enforce_sandbox=not args.no_sandbox,
    )
    suite = _scoring.run_suite(tasks, agents, config=config, label=f"dir={args.dir}")

    # Persisted artifacts (paths go to stderr so --json stdout stays clean JSON).
    if args.out:
        written = _scoring.write_suite_result(suite, args.out)
        print(f"result written: {written}", file=sys.stderr)
    if args.report:
        fmt = _fmt_for_path(args.report)
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_render_suite(suite, fmt), encoding="utf-8")
        print(f"report written: {out} ({fmt})", file=sys.stderr)

    if args.json:
        print(json.dumps(suite.to_dict(), indent=2))
    else:
        print(_render_suite(suite, args.format))

    # A completed suite returns 0; a harness-level error in any run returns 2.
    errored = any(r.outcome == _runtime.RunOutcome.ERROR for r in suite.records)
    return 2 if errored else 0


def _cmd_eval_report(args: argparse.Namespace) -> int:
    try:
        suite = _scoring.load_suite_result(args.path)
    except (OSError, ValueError) as exc:
        print(f"could not load suite result {args.path!r}: {exc}", file=sys.stderr)
        return 1
    text = _render_suite(suite, args.format)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"report written: {out}", file=sys.stderr)
    else:
        print(text)
    return 0


def _cmd_eval_compare(args: argparse.Namespace) -> int:
    """Diff two suite result files — Milestone 9 regression comparison.

    Exit code mirrors the verdict: 1 if any key regressed (a CI-friendly gate),
    0 otherwise. A missing/malformed input file is a load error (exit 1) with a
    message on stderr.
    """
    try:
        baseline = _scoring.load_suite_result(args.baseline)
        candidate = _scoring.load_suite_result(args.candidate)
    except (OSError, ValueError) as exc:
        print(f"could not load suite result: {exc}", file=sys.stderr)
        return 1

    comparison = _scoring.compare_suites(baseline, candidate)

    if args.out:
        written = _scoring.write_comparison(comparison, args.out)
        print(f"comparison written: {written}", file=sys.stderr)
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_reports.regression_to_markdown(comparison), encoding="utf-8")
        print(f"report written: {out}", file=sys.stderr)

    if args.json:
        print(json.dumps(comparison.to_dict(), indent=2))
    else:
        print(_reports.regression_to_markdown(comparison))

    return 1 if comparison.has_regressions else 0


def _cmd_eval_rerun(args: argparse.Namespace) -> int:
    """Re-run the matrix N times and report flaky keys — Milestone 9 rerun mode.

    Exit code is 1 if any key was flaky (non-deterministic across repeats), 0
    otherwise. The deterministic baseline agents yield 0 flaky keys.
    """
    tasks = _select_eval_tasks(args)
    if tasks is None:
        return 1
    if not tasks:
        print(f"No tasks found under {args.dir}/.", file=sys.stderr)
        return 1
    if args.repeats < 1:
        print(f"--repeats must be >= 1, got {args.repeats}", file=sys.stderr)
        return 1

    agents = _scoring.DEFAULT_AGENTS if args.agent == "all" else (args.agent,)
    config = _runtime.RunConfig(
        max_steps=args.max_steps,
        run_tests=not args.no_tests,
        enforce_sandbox=not args.no_sandbox,
    )
    suites = _scoring.run_repeated(
        tasks, agents, repeats=args.repeats, config=config, label=f"dir={args.dir}"
    )
    report = _scoring.analyze_flakiness(suites, label=f"dir={args.dir}")

    if args.out:
        written = _scoring.write_flakiness(report, args.out)
        print(f"flakiness written: {written}", file=sys.stderr)
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_reports.flakiness_to_markdown(report), encoding="utf-8")
        print(f"report written: {out}", file=sys.stderr)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(_reports.flakiness_to_markdown(report))

    return 1 if report.has_flakes else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code.

    With no subcommand, prints help and returns 0 so the bare invocation is
    informative rather than an error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
