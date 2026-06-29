# Fixture: cli_echo

Before-state for the `cli/add-reverse-flag` task. `echo.py` echoes its text and
has no `--reverse` flag. `test_echo.py` exercises both the default and the new
reversed behaviour, so the suite fails until the flag and the matching
`render(reverse=...)` parameter are added. The scripted solution rewrites
`echo.py` to add the flag while keeping the default output unchanged.
