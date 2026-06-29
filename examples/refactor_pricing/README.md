# Fixture: refactor_pricing

Before-state for the `refactor/extract-rate-constant` task. The tax rate `0.07`
is duplicated across `tax_for` and `price_with_tax`. The task extracts it into a
single named constant (`TAX_RATE`) without changing behaviour. It is scored by
the `tests_pass_and_diff_scope` custom scorer: the tests must keep passing **and**
the change must stay inside `pricing.py`. A do-nothing agent keeps the tests
green but fails the scope half (it changed nothing), so the scorer discriminates
a real refactor from no work.
