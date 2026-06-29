# Fixture: number_theory

Before-state for the `bugfix/gcd-modulo-swap` task. The Euclidean loop is right,
but `gcd` returns `b` after it — and `b` is always `0` when the loop exits — so
every call returns `0`. The one-line fix (`return b` → `return a`) makes
`test_number_theory.py` pass; the scripted solution applies exactly that change.
