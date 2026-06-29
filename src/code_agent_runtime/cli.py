"""Command-line interface for Code Agent Runtime.

The CLI is intentionally minimal at this stage. It exposes version/status
commands, the Milestone 1 operational checks (``env-check``, ``hygiene``), the
Milestone 2 task tools (``tasks list`` / ``tasks show``), the Milestone 3 tool
registry (``tools list`` / ``tools show``), the Milestone 4 runtime (``run``)
with optional Milestone 5 trace recording (``run --trace``), and the Milestone 6
trace inspection/replay tooling (``trace show`` / ``trace report``). Full scoring
and suite reporting subcommands are added in later milestones (see
``docs/PLAN.md``).
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
from . import runtime as _runtime
from . import tasks as _tasks
from . import tools as _tools
from . import traces as _traces

# The milestone the runtime currently implements. Kept here so ``info`` can
# report honest project status without scanning the filesystem.
CURRENT_MILESTONE = "Milestone 6 — Replay and debugging tools"
NEXT_MILESTONE = "Milestone 7 — Permission policies and sandbox controls"

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
        choices=["mock", "scripted"],
        default="scripted",
        help="Which deterministic agent to run (default: scripted).",
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

    if args.agent == "mock":
        agent: _agents.Agent = _agents.MockAgent()
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
