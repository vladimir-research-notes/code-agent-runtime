# Fixture: kv_parser

Before-state for the `tests/implement-kv-parser` task. `parse_kv` is a stub that
raises `NotImplementedError`, so `test_kv_parser.py` fails. The task is a
tests-must-pass task: implement the parser (split on commas, partition each pair
on `=`, trim whitespace, ignore empty entries) so the suite goes green. The
scripted solution writes that implementation.
