"""
Tests for the missing null/None checks detection rule.

Tests verify that variables assigned None or from .get() are flagged when
used for attribute access without a null guard, and that proper guards
prevent false positives.
"""

import pytest
from static_analyzer.rules.null_checks import check


class TestNullChecksPython:
    """Tests for Python null-check detection (AST-based)."""

    def test_none_assignment_then_attribute_access(self):
        """Attribute access on a variable assigned None should be flagged."""
        code = '''
def process():
    result = None
    print(result.strip())
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "bug"
        assert "result" in issues[0].message

    def test_get_call_then_attribute_access(self):
        """Attribute access on a .get() result (which may be None) should be flagged."""
        code = '''
def process(data):
    value = data.get("key")
    print(value.strip())
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert "value" in issues[0].message

    def test_none_with_guard_not_flagged(self):
        """'if x is not None' guard should prevent the flag."""
        code = '''
def process():
    result = None
    if result is not None:
        print(result.strip())
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_truthy_guard_not_flagged(self):
        """'if x:' truthiness check should prevent the flag."""
        code = '''
def process():
    result = None
    if result:
        print(result.strip())
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_reassignment_clears_none_status(self):
        """Reassigning to a non-None value should clear the maybe-None status."""
        code = '''
def process():
    x = None
    x = "hello"
    print(x.strip())
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_get_with_default_not_flagged(self):
        """.get(key, default) with an explicit default is NOT maybe-None."""
        code = '''
def process(data):
    value = data.get("key", "default")
    print(value.strip())
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_non_none_assignment_not_flagged(self):
        """Variables assigned non-None values should NOT be flagged."""
        code = '''
def process():
    result = "hello"
    print(result.strip())
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_non_python_returns_empty(self):
        """Non-Python languages should return empty."""
        code = "let x = null; console.log(x.toString());"
        issues = check(code, "javascript")
        assert len(issues) == 0

    def test_module_level_none_check(self):
        """Module-level code (not in a function) should also be checked."""
        code = '''
data = None
print(data.keys())
'''
        issues = check(code, "python")
        assert len(issues) >= 1
