# rules/ — Each module in this package implements a single analysis rule.
# Every rule module exports a `check(code: str, language: str) -> list[Issue]`
# function. This uniform interface lets the analyzer orchestrator discover
# and run all rules without knowing their internals.

from . import (
    hardcoded_secrets,
    sql_injection,
    unused_variables,
    bare_exceptions,
    null_checks,
    infinite_loops,
    mutable_defaults,
    naming_conventions,
)

# All rule modules, in the order they should be run.
# Using an explicit list (instead of auto-discovery) so the execution order
# is deterministic and easy to reason about in tests.
ALL_RULES = [
    hardcoded_secrets,
    sql_injection,
    unused_variables,
    bare_exceptions,
    null_checks,
    infinite_loops,
    mutable_defaults,
    naming_conventions,
]
