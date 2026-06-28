# Fixture: tiny_cli_project

A minimal Python CLI used as the workspace snapshot for the
`cli/add-shout-flag` task.

- `greet.py` — prints `Hello, <name>!`. It has no `--shout` option yet.
- `test_greet.py` — pins the current default behaviour.

The task (`cli/add-shout-flag`) asks an agent to add an optional `--shout` flag
that uppercases the greeting, **without** changing the default output or
breaking the existing tests. This is the *before* state; nothing here is
executed by the Milestone 2 task loader.
