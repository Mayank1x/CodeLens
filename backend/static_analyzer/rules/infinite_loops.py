"""
Rule: Potential Infinite Loop Detection

Detects `while True` loops that have no visible `break`, `return`, `raise`,
or `sys.exit()` statement anywhere in the loop body. Without an exit path,
these loops will run forever and hang the program.

Note: This is a syntactic check, not a semantic one. A loop like
`while True: if condition: break` IS correctly flagged as safe.
But a loop that breaks via an exception raised in a called function
would be a false negative — that's acceptable for a static analyzer
since tracking cross-function control flow requires much deeper analysis.

Supported languages: Python (AST-based), JavaScript (regex-based for
`while(true)` patterns).
"""

import ast
import re
from ..models import Issue


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for potential infinite loops."""
    if language == "python":
        return _check_python_ast(code)
    else:
        return _check_regex(code, language)


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to detect while-True loops without exit paths."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue

        # Check if the condition is `True` (literal boolean True)
        if not _is_true_literal(node.test):
            continue

        # Check if the loop body contains any exit mechanism
        if not _has_exit_path(node):
            issues.append(
                Issue(
                    line_number=node.lineno,
                    severity="warning",
                    category="bug",
                    message=(
                        "'while True' loop with no visible break, return, "
                        "raise, or sys.exit() — this may run forever."
                    ),
                    suggestion=(
                        "Add a 'break' statement with a clear exit condition, "
                        "or use a conditional loop like 'while condition:' instead."
                    ),
                )
            )

    return issues


def _is_true_literal(node: ast.expr) -> bool:
    """Check if an AST expression node is the literal `True`.

    We also check for `1` since `while 1:` is a common C-style idiom
    that some Python developers use.
    """
    if isinstance(node, ast.Constant):
        return node.value is True or node.value == 1
    return False


def _has_exit_path(while_node: ast.While) -> bool:
    """Check if a while loop body contains any statement that could exit the loop.

    We look for:
    - break statements (directly exit the loop)
    - return statements (exit the function, and thus the loop)
    - raise statements (exit via exception)
    - sys.exit() calls (exit the program)

    Important: We only check the DIRECT body of the while loop, not nested
    loops. A `break` inside a nested for/while loop exits that inner loop,
    not the outer while True.
    """
    for node in _walk_excluding_nested_loops(while_node):
        if isinstance(node, ast.Break):
            return True
        if isinstance(node, ast.Return):
            return True
        if isinstance(node, ast.Raise):
            return True
        # sys.exit() or exit() calls
        if isinstance(node, ast.Call):
            if _is_exit_call(node):
                return True

    return False


def _walk_excluding_nested_loops(while_node: ast.While):
    """Walk the AST of a while loop body, but skip nested loop bodies.

    This is necessary because a `break` inside a nested for/while loop
    exits that inner loop, not our outer while-True loop. We need to
    exclude those inner breaks from our check.

    Design: We skip nested loops at BOTH levels — top-level statements
    that are loops, and any loops found deeper in the tree. This prevents
    a break inside `for item in items: if cond: break` from being
    incorrectly counted as an exit for the outer while True.
    """
    for stmt in while_node.body:
        # If a top-level statement in the while body is itself a loop,
        # skip it entirely — any break inside it exits that inner loop
        if isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)):
            continue
        yield from _walk_skip_inner_loops(stmt)


def _walk_skip_inner_loops(node):
    """Recursively yield AST nodes, but skip nested loop subtrees entirely."""
    yield node
    for child in ast.iter_child_nodes(node):
        # Don't descend into nested while/for loop bodies at all.
        # A break inside a nested loop exits that loop, not our outer one.
        if isinstance(child, (ast.While, ast.For, ast.AsyncFor)):
            continue
        yield from _walk_skip_inner_loops(child)


def _is_exit_call(node: ast.Call) -> bool:
    """Check if a Call node is sys.exit() or exit() or quit()."""
    # sys.exit()
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "exit" and isinstance(node.func.value, ast.Name):
            if node.func.value.id in ("sys", "os"):
                return True
    # exit() or quit() builtins
    if isinstance(node.func, ast.Name):
        if node.func.id in ("exit", "quit"):
            return True
    return False


def _check_regex(code: str, language: str) -> list[Issue]:
    """Regex-based infinite loop detection for non-Python languages."""
    issues = []
    lines = code.split("\n")

    # Detect `while(true)` or `while (true)` or `for(;;)` patterns
    infinite_pattern = re.compile(
        r"\b(?:while\s*\(\s*(?:true|1)\s*\)|for\s*\(\s*;\s*;\s*\))", re.IGNORECASE
    )

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue

        if infinite_pattern.search(line):
            # Simple check: look ahead for a break/return in nearby lines
            # This is a rough heuristic for non-Python languages
            context = "\n".join(lines[i - 1 : min(i + 20, len(lines))])
            if not re.search(r"\b(break|return|throw|exit)\b", context):
                issues.append(
                    Issue(
                        line_number=i,
                        severity="warning",
                        category="bug",
                        message=(
                            "Potential infinite loop detected with no visible exit path."
                        ),
                        suggestion=(
                            "Ensure the loop has a break condition or use a "
                            "conditional loop instead."
                        ),
                    )
                )

    return issues
