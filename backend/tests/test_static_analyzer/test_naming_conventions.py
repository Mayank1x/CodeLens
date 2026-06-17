"""
Tests for the inconsistent naming convention detection rule.

Tests verify that mixing snake_case and camelCase in the same file is flagged,
while consistent naming (all snake_case or all camelCase) is NOT flagged.
"""

import pytest
from static_analyzer.rules.naming_conventions import check


class TestNamingConventionsPython:
    """Tests for Python naming convention detection (AST-based)."""

    def test_mixed_snake_and_camel(self):
        """A file with both snake_case and camelCase names should be flagged."""
        code = '''
def get_user_name():
    pass

def getUserAge():
    pass

def calculate_total_price():
    pass
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "info"
        assert issues[0].category == "style"
        assert "inconsistent" in issues[0].message.lower()

    def test_all_snake_case_not_flagged(self):
        """A file with only snake_case names should NOT be flagged."""
        code = '''
def get_user_name():
    pass

def calculate_total_price():
    user_data = {}
    total_count = 0
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_all_camel_case_not_flagged(self):
        """A file with only camelCase names should NOT be flagged."""
        code = '''
def getUserName():
    pass

def calculateTotalPrice():
    userData = {}
    totalCount = 0
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_single_word_names_ignored(self):
        """Single-word names should be ignored (valid in both conventions)."""
        code = '''
def get():
    count = 0
    data = []
    result = None
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_upper_case_constants_ignored(self):
        """UPPER_CASE constants should not affect the convention check."""
        code = '''
MAX_SIZE = 100
API_KEY = "key"

def get_user_data():
    pass

def calculate_total():
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_dunder_names_ignored(self):
        """Dunder names (__init__, __str__) should be ignored."""
        code = '''
class MyClass:
    def __init__(self):
        pass

    def __str__(self):
        pass

    def get_value(self):
        pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_private_names_ignored(self):
        """Private names (_internal) should be ignored."""
        code = '''
def _private_helper():
    pass

def getUserData():
    pass

def processItems():
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_minority_convention_flagged(self):
        """The minority convention should be the one flagged."""
        code = '''
def get_user_name():
    pass

def get_user_age():
    pass

def get_user_email():
    pass

def getUserId():
    pass
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        # getUserId is the minority (camelCase) so it should be flagged
        assert any("getUserId" in i.message for i in issues)

    def test_pascal_case_class_ignored(self):
        """PascalCase class names should not interfere with the check."""
        code = '''
class UserManager:
    def get_all_users(self):
        pass

    def delete_old_users(self):
        pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_syntax_error_returns_empty(self):
        """Broken code should not crash."""
        code = "def broken(:\n    camelCase = 1\n    snake_case = 2"
        issues = check(code, "python")
        assert isinstance(issues, list)
