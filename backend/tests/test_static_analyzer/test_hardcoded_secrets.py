"""
Tests for the hardcoded secrets detection rule.

Each test uses a small, focused code snippet that either should or should not
trigger the rule. This makes it easy to understand exactly what the rule
catches and what it intentionally ignores.
"""

import pytest
from static_analyzer.rules.hardcoded_secrets import check


class TestHardcodedSecretsPython:
    """Tests for Python-specific secret detection (AST-based)."""

    def test_password_in_variable(self):
        """A variable named 'password' assigned a string literal should be flagged."""
        code = 'password = "super_secret_password_123"'
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "critical"
        assert issues[0].category == "security"
        assert "password" in issues[0].message.lower()

    def test_api_key_in_variable(self):
        """A variable named 'api_key' assigned a string literal should be flagged."""
        code = 'api_key = "sk-abc123def456ghi789jkl012mno345pqr"'
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "critical"

    def test_token_in_variable(self):
        """A variable named 'auth_token' should be flagged."""
        code = 'auth_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123"'
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_aws_access_key_pattern(self):
        """An AWS access key ID (AKIA...) should be flagged by value pattern."""
        code = 'key = "AKIAIOSFODNN7EXAMPLE"'
        issues = check(code, "python")
        assert len(issues) >= 1
        assert any("AWS" in i.message for i in issues)

    def test_github_token_pattern(self):
        """A GitHub personal access token (ghp_...) should be flagged."""
        code = 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"'
        issues = check(code, "python")
        assert len(issues) >= 1
        assert any("GitHub" in i.message for i in issues)

    def test_keyword_argument_secret(self):
        """Secrets passed as keyword arguments should be flagged."""
        code = 'connect(password="my_database_password_123")'
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_short_string_not_flagged(self):
        """Short strings (< 8 chars) should NOT be flagged as secrets."""
        code = 'password = "short"'
        issues = check(code, "python")
        assert len(issues) == 0

    def test_non_secret_variable_not_flagged(self):
        """Variables with non-secret names should NOT be flagged."""
        code = 'username = "john_doe_the_developer"'
        issues = check(code, "python")
        assert len(issues) == 0

    def test_integer_assignment_not_flagged(self):
        """Non-string assignments should NOT be flagged."""
        code = "password = 12345678"
        issues = check(code, "python")
        assert len(issues) == 0

    def test_env_var_lookup_not_flagged(self):
        """Loading from environment variables is the SAFE pattern — should NOT be flagged."""
        code = 'password = os.environ.get("PASSWORD")'
        issues = check(code, "python")
        assert len(issues) == 0

    def test_syntax_error_falls_back_to_regex(self):
        """Syntactically broken code should still be scanned via regex fallback."""
        code = 'password = "super_secret_password_123"\ndef broken(:'
        issues = check(code, "python")
        assert len(issues) >= 1


class TestHardcodedSecretsJavaScript:
    """Tests for JavaScript secret detection (regex-based)."""

    def test_const_api_key(self):
        """A const with a secret-like name should be flagged."""
        code = 'const API_KEY = "sk-abc123def456ghi789jkl012mno345pqr";'
        issues = check(code, "javascript")
        assert len(issues) >= 1
        assert issues[0].severity == "critical"

    def test_let_password(self):
        """A let variable named password should be flagged."""
        code = 'let password = "my_secret_password_value";'
        issues = check(code, "javascript")
        assert len(issues) >= 1

    def test_comment_line_not_flagged(self):
        """Comments should not be flagged even if they contain secret-like text."""
        code = '// const password = "not_a_real_secret_value";'
        issues = check(code, "javascript")
        assert len(issues) == 0

    def test_normal_variable_not_flagged(self):
        """Non-secret variable names should not be flagged."""
        code = 'const greeting = "hello world from the app";'
        issues = check(code, "javascript")
        assert len(issues) == 0
