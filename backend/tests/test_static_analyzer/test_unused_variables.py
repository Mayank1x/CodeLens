"""
Tests for the unused variables detection rule.

Tests verify that assigned-but-never-read variables are flagged, while
intentionally unused variables (prefixed with _) and imports are NOT flagged.
"""

import pytest
from static_analyzer.rules.unused_variables import check


class TestUnusedVariablesPython:
    """Tests for Python unused variable detection (AST-based)."""

    def test_simple_unused_variable(self):
        """A variable assigned but never used should be flagged."""
        code = '''
x = 42
print("hello")
'''
        issues = check(code, "python")
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "bug"
        assert "x" in issues[0].message

    def test_used_variable_not_flagged(self):
        """A variable that is assigned and then read should NOT be flagged."""
        code = '''
x = 42
print(x)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_underscore_prefix_not_flagged(self):
        """Variables prefixed with _ are intentionally unused — should NOT be flagged."""
        code = '''
_unused = get_value()
_ = another_call()
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_multiple_unused(self):
        """Multiple unused variables should each be flagged."""
        code = '''
a = 1
b = 2
c = 3
print("none used")
'''
        issues = check(code, "python")
        assert len(issues) == 3

    def test_augmented_assignment_counts_as_read(self):
        """Variables used in += etc. should NOT be flagged."""
        code = '''
count = 0
count += 1
print(count)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_function_def_not_flagged(self):
        """Function definitions should NOT be flagged as unused."""
        code = '''
def my_function():
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_class_def_not_flagged(self):
        """Class definitions should NOT be flagged as unused."""
        code = '''
class MyClass:
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_import_not_flagged(self):
        """Imports should NOT be flagged as unused (that's a separate concern)."""
        code = '''
import os
from sys import path
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_non_python_returns_empty(self):
        """Non-Python languages should return empty (too noisy for regex)."""
        code = "let x = 42;"
        issues = check(code, "javascript")
        assert len(issues) == 0

    def test_syntax_error_returns_empty(self):
        """Syntactically invalid code should return empty, not crash."""
        code = "def broken(:\n    x = 1"
        issues = check(code, "python")
        assert isinstance(issues, list)
