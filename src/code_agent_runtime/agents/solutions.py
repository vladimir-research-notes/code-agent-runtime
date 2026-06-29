"""Built-in scripted solutions for the shipped example tasks (Milestone 4).

These are the "known-good" plans the :class:`~.scripted_agent.ScriptedAgent`
replays to drive a shipped task from its failing fixture to passing tests. They
exist so the runtime has a deterministic, model-free agent that genuinely
*completes* a task end to end — the Milestone 4 validation criterion.

A solution is built from the task itself: a builder may read the task's fixture
on disk to construct an exact patch (the workspace the runtime later prepares is
a copy of that same fixture, so the patch context matches). The agent that
replays the resulting actions stays a dumb, observation-blind replayer; all the
task-specific work happens here, once, before the loop starts. This keeps the
agent/solver boundary clean and every run reproducible.

Only the example tasks have solutions. Asking for a scripted run of a task
without one raises :class:`KeyError` with the list of available ids, rather than
silently doing nothing.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from pathlib import Path

from ..tasks import Task, resolve_fixture
from ..tools import ToolCall
from .scripted_agent import ScriptedAgent

#: Corrected ``greet.py`` for the ``cli/add-shout-flag`` task: adds an optional
#: ``--shout`` flag while preserving the default greeting (so the fixture's
#: existing tests keep passing). Kept as a literal because the change adds new
#: lines and a parameter rather than editing one line in place.
_GREET_WITH_SHOUT = '''\
"""A tiny greeting CLI (task fixture).

The ``cli/add-shout-flag`` task adds an optional ``--shout`` flag while keeping
the default, non-shouting behaviour unchanged.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="greet", description="Print a greeting.")
    parser.add_argument("name", help="who to greet")
    parser.add_argument(
        "--shout", action="store_true", help="print the greeting in uppercase"
    )
    return parser


def format_greeting(name: str, shout: bool = False) -> str:
    """Return the greeting for ``name``; uppercased when ``shout`` is set."""
    greeting = f"Hello, {name}!"
    return greeting.upper() if shout else greeting


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(format_greeting(args.name, shout=args.shout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _unified_diff(rel_path: str, before: str, after: str) -> str:
    """Build a unified diff with ``a/``/``b/`` headers that ``apply_patch`` reads."""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )


def _read_fixture_file(task: Task, rel_path: str) -> str:
    path = Path(resolve_fixture(task)) / rel_path
    return path.read_text(encoding="utf-8")


def _solution_sum_range(task: Task) -> list[ToolCall]:
    """Fix the off-by-one in ``summation.py`` via read → search → apply_patch."""
    before = _read_fixture_file(task, "summation.py")
    after = before.replace("for i in range(1, n):", "for i in range(1, n + 1):")
    if after == before:  # fixture drifted; fail loudly rather than no-op
        raise ValueError(
            "scripted solution for 'bugfix/sum-range-off-by-one' could not locate "
            "the buggy line 'for i in range(1, n):' in the fixture"
        )
    patch = _unified_diff("summation.py", before, after)
    return [
        ToolCall("read_file", {"path": "summation.py"}),
        ToolCall("search_repo", {"query": "range(1, n)"}),
        ToolCall("apply_patch", {"patch": patch}),
    ]


def _solution_add_shout(task: Task) -> list[ToolCall]:
    """Add a ``--shout`` flag to ``greet.py`` via read → write_file."""
    return [
        ToolCall("read_file", {"path": "greet.py"}),
        ToolCall("write_file", {"path": "greet.py", "content": _GREET_WITH_SHOUT}),
    ]


#: Task id → builder. A builder takes the validated task and returns the tool
#: calls a scripted agent should replay to solve it.
SOLUTIONS: dict[str, Callable[[Task], list[ToolCall]]] = {
    "bugfix/sum-range-off-by-one": _solution_sum_range,
    "cli/add-shout-flag": _solution_add_shout,
}


def has_solution(task_id: str) -> bool:
    """True if a built-in scripted solution exists for ``task_id``."""
    return task_id in SOLUTIONS


def build_scripted_agent(task: Task) -> ScriptedAgent:
    """Return a :class:`ScriptedAgent` carrying the solution for ``task``.

    Raises :class:`KeyError` if no built-in solution exists for the task id.
    """
    try:
        builder = SOLUTIONS[task.id]
    except KeyError:
        raise KeyError(
            f"no built-in scripted solution for task {task.id!r} "
            f"(available: {', '.join(sorted(SOLUTIONS)) or 'none'})"
        ) from None
    return ScriptedAgent(builder(task), name="scripted")
