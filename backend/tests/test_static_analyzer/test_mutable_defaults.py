"""
Tests for the mutable default arguments detection rule.

Tests verify that mutable defaults (list, dict, set) in function signatures
are flagged, while safe defaults (None, strings, integers) are NOT.
"""

import pytest
from static_analyzer.rules.mutable_defaults import check


class TestMutableDefaultsPython:
    """Tests for Python mutable default argument detection (AST-based)."""

    def test_list_default(self):
        """A list literal as a default argument should be flagged."""
        code = '''
def append_to(element, target=[]):
    target.append(element)
    return target
'''
        issues = check(code, "python")
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "bug"
        assert "list" in issues[0].message.lower()
        assert "target" in issues[0].message

    def test_dict_default(self):
        """A dict literal as a default argument should be flagged."""
        code = '''
def process(config={}):
    return config
'''
        issues = check(code, "python")
        assert len(issues) == 1
        assert "dict" in issues[0].message.lower()

    def test_set_default(self):
        """A set literal as a default argument should be flagged."""
        code = '''
def collect(seen={1, 2, 3}):
    return seen
'''
        issues = check(code, "python")
        assert len(issues) == 1

    def test_list_constructor_default(self):
        """list() constructor as default should also be flagged."""
        code = '''
def process(items=list()):
    items.append("new")
    return items
'''
        issues = check(code, "python")
        assert len(issues) == 1

    def test_none_default_not_flagged(self):
        """None as default is the SAFE pattern — should NOT be flagged."""
        code = '''
def append_to(element, target=None):
    if target is None:
        target = []
    target.append(element)
    return target
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_string_default_not_flagged(self):
        """String defaults are immutable — should NOT be flagged."""
        code = '''
def greet(name="World"):
    print(f"Hello, {name}!")
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_int_default_not_flagged(self):
        """Integer defaults are immutable — should NOT be flagged."""
        code = '''
def countdown(start=10):
    while start > 0:
        start -= 1
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_tuple_default_not_flagged(self):
        """Tuple defaults are immutable — should NOT be flagged."""
        code = '''
def process(sizes=(1, 2, 3)):
    return sum(sizes)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_multiple_mutable_defaults(self):
        """Multiple mutable defaults in one function should each be flagged."""
        code = '''
def bad_func(a=[], b={}, c=set()):
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 3

    def test_kwonly_mutable_default(self):
        """Keyword-only arguments with mutable defaults should be flagged."""
        code = '''
def process(*, items=[]):
    return items
'''
        issues = check(code, "python")
        assert len(issues) == 1

    def test_async_function_also_checked(self):
        """Async function definitions should also be checked."""
        code = '''
async def fetch_all(urls=[]):
    return urls
'''
        issues = check(code, "python")
        assert len(issues) == 1

    def test_non_python_returns_empty(self):
        """This rule is Python-specific — other languages return empty."""
        code = "function foo(x = []) { return x; }"
        issues = check(code, "javascript")
        assert len(issues) == 0
