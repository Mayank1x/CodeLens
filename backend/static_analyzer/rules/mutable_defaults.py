"""
Rule: Mutable Default Arguments Detection

Detects function definitions that use mutable objects (lists, dicts, sets)
as default argument values. This is a classic Python gotcha: the default
value is evaluated ONCE when the function is defined, not each time it's
called. So all calls that use the default share the SAME mutable object,
leading to subtle and hard-to-debug state-sharing bugs.

Example of the bug:
    def append_to(element, target=[]):  # Dangerous!
        target.append(element)
        return target

    append_to(1)  # Returns [1]
    append_to(2)  # Returns [1, 2] — NOT [2]!

The fix is to use None as the default and create a new mutable inside the body:
    def append_to(element, target=None):
        if target is None:
            target = []
        target.append(element)
        return target

Supported languages: Python only (this is a Python-specific language gotcha).
"""

import ast
from typing import Optional
from ..models import Issue


# The AST node types that represent mutable literal defaults
MUTABLE_AST_TYPES = (ast.List, ast.Dict, ast.Set)


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for mutable default arguments in function definitions."""
    if language != "python":
        # This is a Python-specific issue — other languages handle defaults differently
        return []
    return _check_python_ast(code)


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to find mutable default arguments."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check each default value in the function signature
        # node.args.defaults contains defaults for positional args (aligned to the END)
        # node.args.kw_defaults contains defaults for keyword-only args
        all_defaults = node.args.defaults + [
            d for d in node.args.kw_defaults if d is not None
        ]

        for default in all_defaults:
            mutable_type = _get_mutable_type(default)
            if mutable_type:
                # Find the parameter name for a more helpful message
                param_name = _find_param_name(node, default)
                param_hint = f" for parameter '{param_name}'" if param_name else ""

                issues.append(
                    Issue(
                        line_number=default.lineno,
                        severity="warning",
                        category="bug",
                        message=(
                            f"Mutable default argument ({mutable_type}){param_hint} in "
                            f"function '{node.name}'. The default is shared across all "
                            f"calls, which can cause unexpected behavior."
                        ),
                        suggestion=(
                            f"Use None as the default and create a new {mutable_type} "
                            f"inside the function body: "
                            f"'def {node.name}(..., {param_name or 'param'}=None): "
                            f"if {param_name or 'param'} is None: "
                            f"{param_name or 'param'} = {mutable_type}()'"
                        ),
                    )
                )

    return issues


def _get_mutable_type(node: ast.expr) -> Optional[str]:
    """Determine if an AST node represents a mutable default value.

    Returns a human-readable type name ('list', 'dict', 'set') if mutable,
    or None if the default is safe.
    """
    # Mutable literals: [], {}, set()
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"

    # Mutable constructor calls: list(), dict(), set()
    # Note: We flag these because even though calling list() creates a NEW
    # empty list at definition time, the intent is almost always wrong —
    # the developer expects a new list per call, not a shared one.
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("list", "dict", "set"):
            return node.func.id

    return None


def _find_param_name(func_node, default_node: ast.expr) -> Optional[str]:
    """Find the parameter name associated with a given default value node.

    Python's AST aligns defaults to the END of the positional args list,
    so we need to offset correctly.
    """
    args = func_node.args

    # Check positional arg defaults (aligned to the end of args.args)
    num_positional = len(args.args)
    num_defaults = len(args.defaults)
    offset = num_positional - num_defaults

    for i, default in enumerate(args.defaults):
        if default is default_node and (offset + i) < num_positional:
            return args.args[offset + i].arg

    # Check keyword-only arg defaults
    for i, default in enumerate(args.kw_defaults):
        if default is default_node and i < len(args.kwonlyargs):
            return args.kwonlyargs[i].arg

    return None
