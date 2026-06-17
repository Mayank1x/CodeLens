"""
Rule: Inconsistent Naming Convention Detection

Detects files where multiple naming conventions are mixed, specifically
snake_case and camelCase. Consistent naming makes code easier to read and
signals attention to detail — inconsistency often indicates copy-pasted code
from different sources or a lack of established team standards.

Approach (Python, AST-based):
- Collect all function names and variable names from the AST
- Classify each name as snake_case, camelCase, UPPER_CASE, or other
- If both snake_case AND camelCase names exist in the same file, flag it

We deliberately ignore:
- Single-word names (they're valid in both conventions: `count`, `data`)
- UPPER_CASE names (constants like MAX_SIZE are a separate convention)
- Dunder names (__init__, __str__) which follow Python's own convention
- Names from imports (they may follow the imported library's convention)
- Single-character names (loop variables like `i`, `x`)

Supported languages: Python (AST-based), JavaScript (regex-based).
"""

import ast
import re
from ..models import Issue


# Patterns for classifying naming styles
# snake_case: all lowercase with underscores, e.g., my_function, get_user_data
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")

# camelCase: starts lowercase, has at least one uppercase letter, e.g., myFunction, getUserData
CAMEL_CASE = re.compile(r"^[a-z][a-z0-9]*([A-Z][a-z0-9]*)+$")

# PascalCase: starts uppercase, has mixed case, e.g., MyClass, UserData
# We don't flag this since it's used for class names even in snake_case codebases
PASCAL_CASE = re.compile(r"^[A-Z][a-z0-9]+([A-Z][a-z0-9]+)*$")

# UPPER_CASE: all uppercase with underscores, e.g., MAX_SIZE, API_KEY
UPPER_CASE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for inconsistent naming conventions."""
    if language == "python":
        return _check_python_ast(code)
    elif language in ("javascript", "java", "cpp"):
        return _check_regex(code, language)
    return []


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to collect names and check for convention mixing."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    # Collect names with their locations and classified convention
    snake_names: list[tuple[str, int]] = []  # (name, line_number)
    camel_names: list[tuple[str, int]] = []  # (name, line_number)

    for node in ast.walk(tree):
        # Function/method names
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _classify_name(node.name, node.lineno, snake_names, camel_names)

        # Variable names (in assignments)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            _classify_name(node.id, node.lineno, snake_names, camel_names)

    # Only flag if BOTH conventions are present — a single convention is fine
    if snake_names and camel_names:
        # Report on the minority convention (the one that appears less often)
        # since it's more likely to be the "wrong" one
        if len(camel_names) <= len(snake_names):
            minority = camel_names
            minority_style = "camelCase"
            majority_style = "snake_case"
        else:
            minority = snake_names
            minority_style = "snake_case"
            majority_style = "camelCase"

        issues = []
        # Report each minority-convention name, but cap at 5 to avoid noise
        for name, lineno in minority[:5]:
            issues.append(
                Issue(
                    line_number=lineno,
                    severity="info",
                    category="style",
                    message=(
                        f"Inconsistent naming: '{name}' uses {minority_style} "
                        f"but most names in this file use {majority_style}."
                    ),
                    suggestion=(
                        f"Rename '{name}' to follow the {majority_style} convention "
                        f"used by the rest of the file for consistency."
                    ),
                )
            )

        if len(minority) > 5:
            issues.append(
                Issue(
                    line_number=minority[5][1],
                    severity="info",
                    category="style",
                    message=(
                        f"{len(minority) - 5} more names use {minority_style} "
                        f"while the file predominantly uses {majority_style}."
                    ),
                    suggestion=(
                        f"Consider standardizing all names to {majority_style} "
                        f"for consistency."
                    ),
                )
            )

        return issues

    return []


def _classify_name(
    name: str,
    lineno: int,
    snake_names: list[tuple[str, int]],
    camel_names: list[tuple[str, int]],
) -> None:
    """Classify a name as snake_case, camelCase, or neither (and skip it).

    We deliberately skip single-word names because they're valid in both
    conventions, and single-character names because they're typically
    loop variables or math variables.
    """
    # Skip names we can't meaningfully classify
    if len(name) <= 1:
        return
    if name.startswith("_"):
        return  # Private/dunder names follow their own rules
    if UPPER_CASE.match(name):
        return  # Constants like MAX_SIZE are a separate convention
    if PASCAL_CASE.match(name):
        return  # Class names like MyClass are expected to be PascalCase

    if SNAKE_CASE.match(name):
        snake_names.append((name, lineno))
    elif CAMEL_CASE.match(name):
        camel_names.append((name, lineno))
    # Names that match neither pattern (e.g., single-word like "count") are skipped


def _check_regex(code: str, language: str) -> list[Issue]:
    """Regex-based naming convention check for non-Python languages."""
    lines = code.split("\n")
    snake_names = []
    camel_names = []

    # Simple extraction: look for variable/function declarations
    # This won't catch everything but gets common patterns
    decl_pattern = re.compile(
        r"""(?:(?:const|let|var|function|int|string|void|public|private|static)\s+)"""
        r"""([a-zA-Z_]\w*)"""
    )

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
            continue

        for match in decl_pattern.finditer(line):
            name = match.group(1)
            _classify_name(name, i, snake_names, camel_names)

    if snake_names and camel_names:
        if len(camel_names) <= len(snake_names):
            minority = camel_names
            minority_style = "camelCase"
            majority_style = "snake_case"
        else:
            minority = snake_names
            minority_style = "snake_case"
            majority_style = "camelCase"

        issues = []
        for name, lineno in minority[:5]:
            issues.append(
                Issue(
                    line_number=lineno,
                    severity="info",
                    category="style",
                    message=(
                        f"Inconsistent naming: '{name}' uses {minority_style} "
                        f"but most names in this file use {majority_style}."
                    ),
                    suggestion=(
                        f"Rename '{name}' to follow the {majority_style} convention."
                    ),
                )
            )
        return issues

    return []
