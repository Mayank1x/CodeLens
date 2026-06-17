"""
Rule: Bare/Broad Exception Handling Detection

Detects two dangerous exception handling patterns:
1. Bare `except:` — catches ALL exceptions including SystemExit and
   KeyboardInterrupt, which almost always masks real bugs.
2. `except Exception` with only `pass` in the body — silently swallows all
   standard exceptions, making debugging nearly impossible.

Why this matters: In production code, silently catching all exceptions is
one of the most common causes of "the code runs but does the wrong thing"
bugs. It's much better to catch specific exception types and handle them
explicitly.

Supported languages: Python (AST-based), JavaScript (regex-based for
empty catch blocks).
"""

import ast
from ..models import Issue


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for bare or overly broad exception handling."""
    if language == "python":
        return _check_python_ast(code)
    elif language in ("javascript", "java", "cpp"):
        return _check_regex(code, language)
    return []


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to detect bare and broad exception handlers."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # Case 1: Bare `except:` with no exception type specified
        if node.type is None:
            issues.append(
                Issue(
                    line_number=node.lineno,
                    severity="warning",
                    category="bug",
                    message=(
                        "Bare 'except:' catches all exceptions including "
                        "SystemExit and KeyboardInterrupt."
                    ),
                    suggestion=(
                        "Specify the exception type you expect, e.g., "
                        "'except ValueError:' or at minimum 'except Exception:' "
                        "to avoid catching system-level signals."
                    ),
                )
            )
            continue

        # Case 2: `except Exception` where the body is just `pass`
        # We check for the Exception type by name since it could be referenced
        # in different ways (Exception, builtins.Exception, etc.)
        exception_name = None
        if isinstance(node.type, ast.Name):
            exception_name = node.type.id
        elif isinstance(node.type, ast.Attribute):
            exception_name = node.type.attr

        if exception_name == "Exception" and _body_is_only_pass(node.body):
            issues.append(
                Issue(
                    line_number=node.lineno,
                    severity="warning",
                    category="bug",
                    message=(
                        "'except Exception: pass' silently swallows all errors, "
                        "making bugs invisible."
                    ),
                    suggestion=(
                        "At minimum, log the exception: "
                        "'except Exception as e: logger.error(f\"Unexpected error: {e}\")'. "
                        "Better yet, catch only the specific exception types you expect."
                    ),
                )
            )

    return issues


def _body_is_only_pass(body: list[ast.stmt]) -> bool:
    """Check if an exception handler body contains only a `pass` statement.

    We also treat `...` (Ellipsis) as equivalent to pass, since some developers
    use it as a placeholder with the same semantic meaning.
    """
    if len(body) != 1:
        return False

    stmt = body[0]

    # `pass` statement
    if isinstance(stmt, ast.Pass):
        return True

    # `...` (Ellipsis) used as a pass equivalent
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        if stmt.value.value is ...:
            return True

    return False


def _check_regex(code: str, language: str) -> list[Issue]:
    """Regex-based detection for empty catch blocks in JS/Java/C++.

    Uses a simpler approach than brace-counting: find each `catch` keyword,
    locate its opening `{`, then scan forward for the matching `}` while
    tracking nesting depth. If the body between them is empty (only
    whitespace and comments), flag it.
    """
    import re

    issues = []

    # Find all catch blocks with their body content using a regex.
    # This pattern captures the content between the opening and closing braces
    # of the catch block. It works for simple cases (no nested braces in body).
    # For nested braces, we use a manual scan as fallback.
    catch_positions = [m.end() for m in re.finditer(r'\bcatch\s*\([^)]*\)\s*\{', code)]

    for open_brace_pos in catch_positions:
        # Find the line number of the catch statement
        catch_line = code[:open_brace_pos].count('\n') + 1

        # Scan forward from the opening brace to find the matching closing brace
        depth = 1
        pos = open_brace_pos
        while pos < len(code) and depth > 0:
            if code[pos] == '{':
                depth += 1
            elif code[pos] == '}':
                depth -= 1
            pos += 1

        if depth != 0:
            continue  # Unmatched braces — skip

        # Extract the body between the braces (excluding the braces themselves)
        body = code[open_brace_pos:pos - 1]

        # Remove single-line comments
        body = re.sub(r'//.*', '', body)
        # Remove multi-line comments
        body = re.sub(r'/\*.*?\*/', '', body, flags=re.DOTALL)

        if body.strip() == '':
            issues.append(
                Issue(
                    line_number=catch_line,
                    severity="warning",
                    category="bug",
                    message="Empty catch block silently swallows errors.",
                    suggestion=(
                        "Handle the error or at minimum log it. "
                        "Empty catch blocks make debugging very difficult."
                    ),
                )
            )

    return issues

