"""
Tests for the bare/broad exception handling detection rule.

Tests cover bare `except:`, `except Exception: pass`, and verify that
properly typed exception handlers are NOT flagged.
"""

import pytest
from static_analyzer.rules.bare_exceptions import check


class TestBareExceptionsPython:
    """Tests for Python exception handling detection (AST-based)."""

    def test_bare_except(self):
        """A bare 'except:' should be flagged."""
        code = '''
try:
    risky_operation()
except:
    pass
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "bug"
        assert "bare" in issues[0].message.lower() or "except:" in issues[0].message.lower()

    def test_except_exception_pass(self):
        """'except Exception: pass' should be flagged (silently swallows errors)."""
        code = '''
try:
    risky_operation()
except Exception:
    pass
'''
        issues = check(code, "python")
        assert len(issues) >= 1
        assert "pass" in issues[0].message.lower() or "silently" in issues[0].message.lower()

    def test_except_exception_with_logging_not_flagged(self):
        """'except Exception as e:' with actual handling should NOT be flagged."""
        code = '''
try:
    risky_operation()
except Exception as e:
    logger.error(f"Error: {e}")
    raise
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_specific_exception_not_flagged(self):
        """Catching a specific exception type should NOT be flagged."""
        code = '''
try:
    int("abc")
except ValueError:
    print("Invalid input")
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_specific_exception_with_pass_not_flagged(self):
        """Catching a specific type with pass is intentional — NOT flagged."""
        code = '''
try:
    os.remove("temp.txt")
except FileNotFoundError:
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_multiple_except_blocks(self):
        """Multiple problematic except blocks should each be flagged."""
        code = '''
try:
    step1()
except:
    pass

try:
    step2()
except Exception:
    pass
'''
        issues = check(code, "python")
        assert len(issues) == 2

    def test_except_exception_with_body_not_flagged(self):
        """except Exception with non-trivial body should NOT be flagged."""
        code = '''
try:
    connect()
except Exception:
    retry_count += 1
    time.sleep(1)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_syntax_error_returns_empty(self):
        """Broken code should return empty, not crash."""
        code = "try:\n    x\nexcept\n    pass"
        issues = check(code, "python")
        assert isinstance(issues, list)


class TestBareExceptionsJavaScript:
    """Tests for JavaScript empty catch block detection (regex-based)."""

    def test_empty_catch_block(self):
        """An empty catch block should be flagged."""
        code = '''try {
    riskyOp();
} catch (e) {
}'''
        issues = check(code, "javascript")
        assert len(issues) >= 1

    def test_catch_with_handling_not_flagged(self):
        """A catch block with actual code should NOT be flagged."""
        code = '''try {
    riskyOp();
} catch (e) {
    console.error(e);
}'''
        issues = check(code, "javascript")
        assert len(issues) == 0
