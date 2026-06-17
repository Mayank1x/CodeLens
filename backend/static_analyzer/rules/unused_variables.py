"""
Rule: Unused Variables Detection

Detects variables that are assigned a value but never subsequently read.
Unused variables often indicate dead code, copy-paste errors, or incomplete
refactoring — all of which reduce code readability and can hide bugs.

Approach (Python, AST-based):
We walk the AST and track every Name node in Store context (assignments) vs
Load context (reads). A variable is "unused" if it appears in Store but never
in Load within the same scope.

Exceptions (deliberately NOT flagged):
- Names starting with `_` (Python convention for intentionally unused values)
- `__all__`, `__name__`, and other dunder names (module-level metadata)
- Loop variables in `for _ in range(...)` patterns
- Names in `__init__` self assignments (self.x = x)

Supported languages: Python only (AST-based). Other languages return empty
because reliable unused-variable detection without a full type system is
too noisy to be useful.
"""

import ast
from ..models import Issue


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for unused variables."""
    if language != "python":
        # Regex-based unused variable detection for non-Python languages
        # produces too many false positives to be useful. Better to skip
        # than to output noise.
        return []
    return _check_python_ast(code)


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to find variables that are assigned but never read."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    # We analyze at the module level for simplicity in v1.
    # A more sophisticated version would track scopes per function/class,
    # but module-level analysis catches the majority of real-world cases.
    assigned = {}  # name -> line_number of first assignment
    loaded = set()  # names that are read at least once

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                # Only record the first assignment location for cleaner messages
                if node.id not in assigned:
                    assigned[node.id] = node.lineno
            elif isinstance(node.ctx, ast.Load):
                loaded.add(node.id)
        # Also track names used in function decorators, base classes, etc.
        # These count as "reads" even though they're not ast.Name(Load) directly
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # The function name itself is "used" if it's called or referenced elsewhere.
            # We don't flag function definitions as unused since that requires
            # call-graph analysis which is beyond the scope of static analysis.
            loaded.add(node.name)
        elif isinstance(node, ast.ClassDef):
            loaded.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name.split(".")[0]
                # Don't flag imports as unused — that's a separate concern
                # and Python IDEs already handle it well
                loaded.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                loaded.add(name)
        # Track augmented assignments (+=, -=, etc.) as both read and write
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                loaded.add(node.target.id)

    # Find variables that were assigned but never loaded
    for name, lineno in sorted(assigned.items(), key=lambda x: x[1]):
        if name in loaded:
            continue
        if _should_ignore(name):
            continue

        issues.append(
            Issue(
                line_number=lineno,
                severity="warning",
                category="bug",
                message=f"Variable '{name}' is assigned but never used.",
                suggestion=(
                    f"Remove the variable '{name}' if it's no longer needed, or "
                    f"prefix it with '_' (e.g., '_{name}') to indicate it's "
                    f"intentionally unused."
                ),
            )
        )

    return issues


def _should_ignore(name: str) -> bool:
    """Check if a variable name should be excluded from unused-variable checks.

    We deliberately skip:
    - Names starting with _ (Python convention for "I know this is unused")
    - Dunder names (__all__, __name__, etc.) which are module-level metadata
    """
    if name.startswith("_"):
        return True
    return False
