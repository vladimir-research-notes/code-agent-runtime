# Fixture: text_utils

Before-state for the `tests/implement-slugify` task. `slugify` is a stub that
raises `NotImplementedError`, so `test_slugify.py` fails. The task is a
tests-must-pass task: implement the function so the suite goes green. The
scripted solution writes the one-line implementation
(`"-".join(text.lower().split())`).
