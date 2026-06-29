"""The ``test_command`` scorer (Milestone 8).

Pass iff the task's test command exited zero. This is the primary, highest-signal
scoring method: a real test suite that goes from red to green is strong evidence
the change is correct. It is the method the Milestone 4 runtime already scored
inline; that logic now lives here so all scoring shares one home.
"""

from __future__ import annotations

from .scorer import ScoreInput, ScoreVerdict, failed, passed


def score_test_command(inp: ScoreInput) -> ScoreVerdict:
    """Score by the test command's exit status (``passed`` in the result data)."""
    tests = inp.tests
    if tests is None:
        return failed(
            "test_command",
            "no test result (the test command did not run)",
        )
    if tests.get("timed_out"):
        return failed("test_command", "test command timed out")
    if tests.get("passed"):
        return passed("test_command", "test command passed", exit_code=tests.get("exit_code"))
    return failed(
        "test_command",
        f"test command failed (exit {tests.get('exit_code')})",
        exit_code=tests.get("exit_code"),
    )
