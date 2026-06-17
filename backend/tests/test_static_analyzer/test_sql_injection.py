"""
Tests for the SQL injection risk detection rule.

Tests cover all four dangerous patterns (f-strings, concatenation, %-formatting,
.format()) and verify that safe parameterized queries are NOT flagged.
"""

import pytest
from static_analyzer.rules.sql_injection import check


class TestSQLInjectionPython:
    """Tests for Python SQL injection detection (AST-based)."""

    def test_fstring_in_execute(self):
        """f-string interpolation in execute() should be flagged."""
        code = '''
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "critical"
        assert issues[0].category == "security"

    def test_concatenation_in_execute(self):
        """String concatenation in execute() should be flagged."""
        code = '''
cursor.execute("SELECT * FROM users WHERE name = '" + name + "'")
'''
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_percent_formatting_in_execute(self):
        """%-formatting in execute() should be flagged."""
        code = '''
cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)
'''
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_format_method_in_execute(self):
        """.format() in execute() should be flagged."""
        code = '''
cursor.execute("SELECT * FROM users WHERE id = {}".format(user_id))
'''
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_parameterized_query_not_flagged(self):
        """Safe parameterized queries should NOT be flagged."""
        code = '''
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_constant_string_query_not_flagged(self):
        """A plain string constant in execute() is safe."""
        code = '''
cursor.execute("SELECT * FROM users")
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_db_execute_also_caught(self):
        """Any .execute() call should be checked, not just cursor.execute()."""
        code = '''
db.execute(f"DELETE FROM sessions WHERE user_id = {uid}")
'''
        issues = check(code, "python")
        assert len(issues) >= 1

    def test_non_execute_call_not_flagged(self):
        """f-strings in non-execute calls should NOT be flagged."""
        code = '''
print(f"User {name} logged in")
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_syntax_error_falls_back(self):
        """Broken Python code should fall back to regex scanning."""
        code = '''cursor.execute("SELECT " + name)\ndef broken(:'''
        issues = check(code, "python")
        # May or may not find issues via regex, but should not crash
        assert isinstance(issues, list)


class TestSQLInjectionJavaScript:
    """Tests for JavaScript SQL injection detection (regex-based)."""

    def test_concatenation_in_query(self):
        """String concatenation in .query() should be flagged."""
        code = 'db.query("SELECT * FROM users WHERE id = " + userId);'
        issues = check(code, "javascript")
        assert len(issues) >= 1

    def test_parameterized_not_flagged(self):
        """Normal code without SQL patterns should not be flagged."""
        code = 'const result = await db.query("SELECT 1");'
        issues = check(code, "javascript")
        assert len(issues) == 0
