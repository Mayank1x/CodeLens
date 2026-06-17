"""
Rule: Missing Null/None Checks Detection

Detects patterns where a variable could be None and is then used for
attribute access without a guard. This is a common source of
AttributeError / NullPointerException crashes in production.

Patterns detected (Python, AST-based):
1. Explicit None assignment followed by unguarded attribute access:
   x = None; ... x.something  (without an `if x` guard in between)
2. Assignment from .get() (which returns None by default) followed by
   unguarded attribute access:
   x = dict.get("key"); ... x.something

Limitations:
- This is a simplified intra-function analysis. A full null-safety analysis
  would require data-flow analysis across function boundaries, which is
  beyond the scope of this static analyzer.
- We only track simple variable names (not attributes or subscripts).

Supported languages: Python only (AST-based).
"""

import ast
from ..models import Issue


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for missing null/None checks before attribute access."""
    if language != "python":
        return []
    return _check_python_ast(code)


def _check_python_ast(code: str) -> list[Issue]:
    """Detect potentially-None variables used without null checks."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    # Analyze each function body independently, since variables in different
    # functions are in different scopes.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            issues.extend(_analyze_function_body(node))

    # Also analyze module-level code (statements not inside any function)
    module_stmts = [
        stmt
        for stmt in tree.body
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if module_stmts:
        issues.extend(_analyze_statements(module_stmts))

    return issues


def _analyze_function_body(func_node) -> list[Issue]:
    """Analyze a single function's body for null-check issues."""
    return _analyze_statements(func_node.body)


def _analyze_statements(statements: list[ast.stmt]) -> list[Issue]:
    """Walk a flat list of statements tracking potentially-None variables.

    Strategy:
    - When we see `x = None` or `x = something.get(...)`, mark x as "maybe None".
    - When we see `x = <non-None value>`, remove x from the "maybe None" set.
    - When we see `if x is not None:` or `if x:`, remove x from "maybe None"
      within that branch.
    - When we see `x.attr` while x is in the "maybe None" set, flag it.
    """
    issues = []
    maybe_none: dict[str, int] = {}  # variable name -> line of None assignment

    for stmt in statements:
        _process_statement(stmt, maybe_none, issues)

    return issues


def _process_statement(
    stmt: ast.stmt, maybe_none: dict[str, int], issues: list[Issue]
) -> None:
    """Process a single statement, updating the maybe_none set and collecting issues."""

    # Assignment: x = None or x = something.get(...)
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                if _is_none_value(stmt.value):
                    maybe_none[target.id] = stmt.lineno
                elif _is_get_call(stmt.value):
                    maybe_none[target.id] = stmt.lineno
                else:
                    # Reassigned to a non-None value, so it's safe now
                    maybe_none.pop(target.id, None)

    # If statement: `if x is not None:` or `if x:` acts as a null guard
    elif isinstance(stmt, ast.If):
        guarded_names = _extract_null_guards(stmt.test)
        # The guarded names are safe inside the if-body, but we don't
        # do full branch analysis in v1 — we just remove them from
        # maybe_none globally (conservative approach: fewer false positives)
        if guarded_names:
            for name in guarded_names:
                maybe_none.pop(name, None)

    # Check all expressions in this statement for attribute access on maybe-None vars
    for node in ast.walk(stmt):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in maybe_none:
                issues.append(
                    Issue(
                        line_number=node.lineno,
                        severity="warning",
                        category="bug",
                        message=(
                            f"Variable '{node.value.id}' may be None (assigned at "
                            f"line {maybe_none[node.value.id]}) but is used for "
                            f"attribute access without a null check."
                        ),
                        suggestion=(
                            f"Add a null check before accessing attributes: "
                            f"'if {node.value.id} is not None: "
                            f"{node.value.id}.{node.attr}'"
                        ),
                    )
                )


def _is_none_value(node: ast.expr) -> bool:
    """Check if an AST node represents a None literal."""
    return isinstance(node, ast.Constant) and node.value is None


def _is_get_call(node: ast.expr) -> bool:
    """Check if an AST node is a .get() method call.

    dict.get() returns None by default when the key is missing, so the
    return value should be treated as potentially None.
    """
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "get":
            # Only flag .get() calls with a single argument (no default value).
            # .get(key, default) with an explicit default is usually intentional.
            if len(node.args) <= 1 and not node.keywords:
                return True
    return False


def _extract_null_guards(test: ast.expr) -> set[str]:
    """Extract variable names that are null-checked in an if-condition.

    Recognizes patterns:
    - `if x is not None`
    - `if x is None` (inverse, but still a guard)
    - `if x:` (truthy check, implicitly guards against None)
    - `if x is not None and y is not None`
    """
    guarded = set()

    # `if x is not None` or `if x is None`
    if isinstance(test, ast.Compare):
        if isinstance(test.left, ast.Name):
            for op, comparator in zip(test.ops, test.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and _is_none_value(comparator):
                    guarded.add(test.left.id)

    # `if x:` (truthy check)
    elif isinstance(test, ast.Name):
        guarded.add(test.id)

    # `if x and y` — both are guarded
    elif isinstance(test, ast.BoolOp):
        for value in test.values:
            guarded.update(_extract_null_guards(value))

    # `if not x` — x is being checked (albeit inversely)
    elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        guarded.update(_extract_null_guards(test.operand))

    return guarded
