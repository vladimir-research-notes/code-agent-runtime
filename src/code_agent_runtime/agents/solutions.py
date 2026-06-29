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


#: Corrected ``echo.py`` for the ``cli/add-reverse-flag`` task: adds an optional
#: ``--reverse`` flag and the matching ``render`` parameter while keeping the
#: default behaviour unchanged.
_ECHO_WITH_REVERSE = '''\
"""A tiny echo CLI (task fixture).

The ``cli/add-reverse-flag`` task adds an optional ``--reverse`` flag (and the
matching ``render`` parameter) while keeping the default behaviour unchanged.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="echo", description="Echo text.")
    parser.add_argument("text", help="text to echo")
    parser.add_argument(
        "--reverse", action="store_true", help="print the text reversed"
    )
    return parser


def render(text: str, reverse: bool = False) -> str:
    """Return the text to print; reversed when ``reverse`` is set."""
    return text[::-1] if reverse else text


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(render(args.text, reverse=args.reverse))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

#: Refactored ``pricing.py`` for ``refactor/extract-rate-constant``: the duplicated
#: ``0.07`` literal is replaced by a single module-level constant, behaviour
#: unchanged.
_PRICING_WITH_CONSTANT = '''\
"""Pricing helpers (task fixture).

The ``refactor/extract-rate-constant`` task extracts the duplicated tax rate into
a single named constant without changing behaviour.
"""

from __future__ import annotations

TAX_RATE = 0.07


def tax_for(amount: float) -> float:
    """Return the tax owed on ``amount``."""
    return amount * TAX_RATE


def price_with_tax(amount: float) -> float:
    """Return ``amount`` plus its tax."""
    return amount + amount * TAX_RATE
'''

#: Implemented ``slugify.py`` for ``tests/implement-slugify``.
_SLUGIFY_IMPL = '''\
"""A slugify helper (task fixture).

Implements the ``tests/implement-slugify`` task: lower-case the text, split on
runs of whitespace, and join the words with single hyphens.
"""

from __future__ import annotations


def slugify(text: str) -> str:
    """Return a hyphenated, lower-cased slug of ``text``."""
    return "-".join(text.lower().split())
'''

#: Implemented ``kv_parser.py`` for ``tests/implement-kv-parser``.
_KV_PARSER_IMPL = '''\
"""A key/value parser (task fixture).

Implements the ``tests/implement-kv-parser`` task: split on commas, partition each
pair on the first ``=``, trim whitespace, and ignore empty entries.
"""

from __future__ import annotations


def parse_kv(text: str) -> dict[str, str]:
    """Parse ``"a=1, b=2"`` into ``{"a": "1", "b": "2"}``."""
    result: dict[str, str] = {}
    for pair in text.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, _, value = pair.partition("=")
        result[key.strip()] = value.strip()
    return result
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


def _replace_solution(
    rel_path: str, old: str, new: str, *, search: str | None = None
) -> Callable[[Task], list[ToolCall]]:
    """Build a one-edit solution that ``read``s a file and ``apply_patch``es a
    single in-place substring replacement.

    The patch is computed from the *fixture's* current contents (the prepared
    workspace is a copy of it, so the context matches). If ``old`` is not found,
    the builder fails loudly rather than emitting an empty patch — a guard against
    fixture drift. An optional ``search`` query inserts a ``search_repo`` step, so
    the replayed plan reads as locate → inspect → edit.
    """

    def builder(task: Task) -> list[ToolCall]:
        before = _read_fixture_file(task, rel_path)
        after = before.replace(old, new)
        if after == before:
            raise ValueError(
                f"scripted solution could not locate {old!r} in fixture file {rel_path!r}"
            )
        patch = _unified_diff(rel_path, before, after)
        calls = [ToolCall("read_file", {"path": rel_path})]
        if search is not None:
            calls.append(ToolCall("search_repo", {"query": search}))
        calls.append(ToolCall("apply_patch", {"patch": patch}))
        return calls

    return builder


def _write_solution(rel_path: str, content: str) -> Callable[[Task], list[ToolCall]]:
    """Build a solution that ``read``s a file and ``write_file``s a full rewrite.

    Used where the change adds structure (new parameters, a constant, a whole
    implementation) rather than editing one line, mirroring ``_solution_add_shout``.
    """

    def builder(_task: Task) -> list[ToolCall]:
        return [
            ToolCall("read_file", {"path": rel_path}),
            ToolCall("write_file", {"path": rel_path, "content": content}),
        ]

    return builder


#: Task id → builder. A builder takes the validated task and returns the tool
#: calls a scripted agent should replay to solve it. Because a builder works from
#: the task's *fixture* (not its id), one builder serves every task over the same
#: fixture — so the Milestone 8 scoring variants (same fix, different
#: ``scoring_method``) reuse the original solutions rather than duplicating them.
SOLUTIONS: dict[str, Callable[[Task], list[ToolCall]]] = {
    "bugfix/sum-range-off-by-one": _solution_sum_range,
    "bugfix/sum-range-expected-files": _solution_sum_range,
    "refactor/sum-range-diff-scope": _solution_sum_range,
    "cli/add-shout-flag": _solution_add_shout,
    "cli/add-shout-flag-custom": _solution_add_shout,
    # Milestone 12 case-study tasks.
    "bugfix/temp-convert-ratio": _replace_solution(
        "temperature.py",
        "return c * 5 / 9 + 32  # BUG: should be c * 9 / 5 + 32",
        "return c * 9 / 5 + 32",
        search="5 / 9",
    ),
    "bugfix/gcd-modulo-swap": _replace_solution(
        "number_theory.py",
        "return b  # BUG: loop ends with b == 0; should return a",
        "return a",
        search="return b",
    ),
    "refactor/extract-rate-constant": _write_solution("pricing.py", _PRICING_WITH_CONSTANT),
    "cli/add-reverse-flag": _write_solution("echo.py", _ECHO_WITH_REVERSE),
    "tests/implement-slugify": _write_solution("slugify.py", _SLUGIFY_IMPL),
    "tests/implement-kv-parser": _write_solution("kv_parser.py", _KV_PARSER_IMPL),
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
