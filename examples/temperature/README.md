# Fixture: temperature

Before-state for the `bugfix/temp-convert-ratio` task. `celsius_to_fahrenheit`
uses the inverted ratio `5 / 9` instead of `9 / 5`, so `test_temperature.py`
fails. The one-line fix (`c * 5 / 9 + 32` → `c * 9 / 5 + 32`) makes the tests
pass; the scripted solution applies exactly that change.
