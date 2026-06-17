"""
Rule: SQL Injection Risk Detection

Detects potential SQL injection vulnerabilities where user input could be
interpolated directly into SQL queries instead of using parameterized queries.

Dangerous patterns detected:
- String concatenation in execute() calls: cursor.execute("SELECT " + user_input)
- f-string formatting in execute() calls: cursor.execute(f"SELECT {user_input}")
- %-formatting in execute() calls: cursor.execute("SELECT %s" % user_input)
- .format() in execute() calls: cursor.execute("SELECT {}".format(user_input))

Safe pattern (NOT flagged): cursor.execute("SELECT %s", (user_input,))
The key difference is that parameterized queries pass values as a separate
tuple argument, letting the database driver handle escaping.

Supported languages: Python (AST-based), JavaScript/Java/C++ (regex-based).
"""

import ast
import re
from ..models import Issue


# SQL keywords that indicate a query string (used in regex fallback)
SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC)\b", re.IGNORECASE
)


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for SQL injection vulnerabilities."""
    if language == "python":
        return _check_python_ast(code)
    else:
        return _check_regex(code, language)


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to detect unsafe SQL query construction."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _check_regex(code, "python")

    for node in ast.walk(tree):
        # Look for calls like cursor.execute(...) or db.execute(...)
        if not isinstance(node, ast.Call):
            continue

        if not _is_execute_call(node):
            continue

        # If there are no arguments, skip (can't have SQL injection with no query)
        if not node.args:
            continue

        query_arg = node.args[0]

        # Check if the query argument uses unsafe string construction
        if _is_unsafe_string_construction(query_arg):
            issues.append(
                Issue(
                    line_number=node.lineno,
                    severity="critical",
                    category="security",
                    message=(
                        "Potential SQL injection: query is built using string "
                        "formatting/concatenation instead of parameterized queries."
                    ),
                    suggestion=(
                        "Use parameterized queries instead: "
                        'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,)). '
                        "This lets the database driver handle escaping safely."
                    ),
                )
            )

    return issues


def _is_execute_call(node: ast.Call) -> bool:
    """Check if a Call node is a .execute() method call.

    Matches patterns like cursor.execute(), db.execute(), conn.execute(), etc.
    We intentionally match ANY .execute() call rather than requiring specific
    receiver names, because database cursors can be named anything.
    """
    # Method call: something.execute(...)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
        return True
    # Direct call: execute(...) — less common but possible with imports
    if isinstance(node.func, ast.Name) and node.func.id == "execute":
        return True
    return False


def _is_unsafe_string_construction(node: ast.expr) -> bool:
    """Check if an AST node represents unsafe string building for SQL.

    Returns True if the node is:
    - An f-string (JoinedStr) — e.g., f"SELECT * FROM {table}"
    - A BinOp with string concatenation (+) — e.g., "SELECT " + var
    - A BinOp with %-formatting (%) — e.g., "SELECT %s" % var
    - A .format() call — e.g., "SELECT {}".format(var)
    """
    # f-string: f"SELECT * FROM {table}"
    if isinstance(node, ast.JoinedStr):
        return True

    # String concatenation with +: "SELECT " + user_input
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            # At least one side should look like a string (constant or another concat)
            return True
        # %-formatting: "query %s" % value
        if isinstance(node.op, ast.Mod):
            return True

    # .format() call: "SELECT {}".format(var)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            # Check if the object being formatted is a string constant
            if isinstance(node.func.value, ast.Constant) and isinstance(
                node.func.value.value, str
            ):
                return True

    return False


def _check_regex(code: str, language: str) -> list[Issue]:
    """Regex-based SQL injection detection for non-Python languages."""
    issues = []
    lines = code.split("\n")

    # Pattern: execute/query call with string concatenation or interpolation
    # This catches common patterns across JS, Java, and C++
    execute_pattern = re.compile(
        r"""\.(?:execute|query|prepare)\s*\(\s*(?:"""
        r"""["'`].*["'`]\s*\+|"""  # String concatenation: "..." +
        r"""\$\{|"""  # Template literal: ${
        r"""["'`].*["'`]\s*%|"""  # %-formatting
        r""".*\.format\s*\()""",  # .format()
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
            continue

        if execute_pattern.search(line) and SQL_KEYWORDS.search(line):
            issues.append(
                Issue(
                    line_number=i,
                    severity="critical",
                    category="security",
                    message=(
                        "Potential SQL injection: query appears to use string "
                        "concatenation or interpolation."
                    ),
                    suggestion=(
                        "Use parameterized/prepared statements instead of "
                        "building query strings manually."
                    ),
                )
            )

    return issues
