# Fixture: tiny_python_bug

A minimal Python repo with one deliberate **off-by-one bug**, used as the
workspace snapshot for the `bugfix/sum-range-off-by-one` task.

- `summation.py` — `sum_to(n)` should return `1 + 2 + ... + n`, but the loop
  uses `range(1, n)` and so drops the final term.
- `test_summation.py` — fails against the buggy code; passes once the loop is
  `range(1, n + 1)`.

This is the *before* state. A run materialises a copy of this directory as the
agent's workspace (Milestone 4); the task is scored by running the tests
(`python3 -m pytest -q`) in that workspace (Milestone 8). Nothing here is run by
the Milestone 2 task loader — it only validates that this fixture path exists.
