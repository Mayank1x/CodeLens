"""
Rule: Hardcoded Secrets / Credentials Detection

Detects potential secrets, API keys, passwords, and tokens that are hardcoded
as string literals in source code. This is a security-critical rule because
hardcoded secrets in version control are one of the most common causes of
data breaches.

Approach: We use two complementary strategies:
1. Variable-name matching — flag assignments where the variable name suggests
   a secret (e.g., `password`, `api_key`, `secret`) and the value is a string literal.
2. Value-pattern matching — flag string literals that match known secret formats
   (e.g., AWS access keys start with "AKIA", GitHub tokens start with "ghp_").

Supported languages: Python (AST-based), JavaScript/Java/C++ (regex-based).
"""

import ast
import re
from ..models import Issue


# Variable names that strongly suggest the value is a secret.
# Using lowercase comparison so `API_KEY`, `api_key`, and `ApiKey` all match.
SECRET_VAR_PATTERNS = re.compile(
    r"(password|passwd|pwd|secret|api_key|apikey|api_secret|"
    r"access_key|access_token|auth_token|token|private_key|"
    r"client_secret|db_password|database_password|encryption_key)",
    re.IGNORECASE,
)

# Known formats for specific credential types.
# Each tuple is (pattern, description) for better error messages.
SECRET_VALUE_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "GitHub Personal Access Token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI/Stripe Secret Key"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "Slack Token"),
    (re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"), "Private Key"),
]

# Minimum length for a string to be considered a potential secret value.
# Short strings like "test" or "" are almost certainly not real secrets.
MIN_SECRET_LENGTH = 8


def check(code: str, language: str) -> list[Issue]:
    """Analyze code for hardcoded secrets and credentials."""
    if language == "python":
        return _check_python_ast(code)
    else:
        # For JS, Java, C++: use regex-based detection
        return _check_regex(code, language)


def _check_python_ast(code: str) -> list[Issue]:
    """Use Python's AST to precisely detect hardcoded secrets in assignments."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # If the code doesn't parse, fall back to regex-based detection.
        # This is a deliberate design choice: we still want to catch obvious
        # secrets even in syntactically broken code.
        return _check_regex(code, "python")

    for node in ast.walk(tree):
        # Check simple assignments like: password = "my_secret_123"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    _check_variable_assignment(
                        target.id, node.value.value, node.lineno, issues
                    )
        # Check keyword arguments like: connect(password="my_secret_123")
        elif isinstance(node, ast.keyword):
            if node.arg and isinstance(node.value, ast.Constant):
                _check_variable_assignment(
                    node.arg, node.value.value, node.value.lineno, issues
                )

    # Also scan all string literals for known secret patterns
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            _check_value_patterns(node.value, node.lineno, issues)

    return issues


def _check_variable_assignment(
    var_name: str, value, lineno: int, issues: list[Issue]
) -> None:
    """Check if a variable assignment looks like a hardcoded secret."""
    if not isinstance(value, str) or len(value) < MIN_SECRET_LENGTH:
        return

    if SECRET_VAR_PATTERNS.search(var_name):
        issues.append(
            Issue(
                line_number=lineno,
                severity="critical",
                category="security",
                message=f"Hardcoded secret detected in variable '{var_name}'.",
                suggestion=(
                    "Move this value to an environment variable and load it with "
                    "os.environ.get() or a .env file. Never commit secrets to version control."
                ),
            )
        )


def _check_value_patterns(value: str, lineno: int, issues: list[Issue]) -> None:
    """Check if a string literal matches known secret formats."""
    for pattern, description in SECRET_VALUE_PATTERNS:
        if pattern.search(value):
            issues.append(
                Issue(
                    line_number=lineno,
                    severity="critical",
                    category="security",
                    message=f"Possible {description} found in string literal.",
                    suggestion=(
                        "Store credentials in environment variables or a secrets manager, "
                        "not in source code."
                    ),
                )
            )
            # Only report one match per string to avoid duplicate noise
            break


def _check_regex(code: str, language: str) -> list[Issue]:
    """Regex-based secret detection for non-Python languages."""
    issues = []
    lines = code.split("\n")

    # Pattern: variable assignment with a secret-looking name and string value
    # Matches patterns like: const API_KEY = "value", String password = "value", etc.
    assignment_pattern = re.compile(
        r"""(?:const|let|var|final|static|private|public|protected|\w+)?\s*"""
        r"""(\w*(?:password|passwd|pwd|secret|api_key|apikey|token|access_key|"""
        r"""private_key|client_secret|auth_token)\w*)\s*=\s*["'`](.{8,})["'`]""",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines, start=1):
        # Skip comment lines (basic heuristic — not perfect but catches most cases)
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
            continue

        match = assignment_pattern.search(line)
        if match:
            var_name = match.group(1)
            issues.append(
                Issue(
                    line_number=i,
                    severity="critical",
                    category="security",
                    message=f"Hardcoded secret detected in variable '{var_name}'.",
                    suggestion=(
                        "Move this value to an environment variable. "
                        "Never commit secrets to version control."
                    ),
                )
            )

        # Check for known secret value patterns in any string literal
        for pattern, description in SECRET_VALUE_PATTERNS:
            if pattern.search(line):
                issues.append(
                    Issue(
                        line_number=i,
                        severity="critical",
                        category="security",
                        message=f"Possible {description} found in string literal.",
                        suggestion=(
                            "Store credentials in environment variables or a secrets manager."
                        ),
                    )
                )
                break  # One match per line is enough

    return issues
