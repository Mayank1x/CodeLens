"""
Performance and integration test for the StaticAnalyzer orchestrator.

Verifies that:
1. The analyzer correctly aggregates results from all rules.
2. Results are sorted by line number and severity.
3. Duplicates are removed.
4. Analysis of a 200-line file completes in under 50ms (spec requirement).
"""

import pytest
import time
from static_analyzer.analyzer import StaticAnalyzer


class TestAnalyzerIntegration:
    """Integration tests for the full analyzer pipeline."""

    def setup_method(self):
        """Create a fresh analyzer instance for each test."""
        self.analyzer = StaticAnalyzer()

    def test_clean_code_returns_empty(self):
        """Well-written code should produce no issues."""
        code = '''
def greet(name: str) -> str:
    """Return a greeting message."""
    message = f"Hello, {name}!"
    return message


def add(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b
'''
        issues = self.analyzer.analyze(code, "python")
        assert len(issues) == 0

    def test_buggy_code_catches_multiple_issues(self):
        """Code with multiple problems should produce multiple issues."""
        code = '''
password = "super_secret_password_123"

def process(data=[]):
    try:
        result = data.get("key")
        cursor.execute(f"SELECT * FROM users WHERE id = {result}")
    except:
        pass

while True:
    x = 1
'''
        issues = self.analyzer.analyze(code, "python")
        # Should catch: hardcoded secret, mutable default, SQL injection,
        # bare except, potentially infinite loop
        assert len(issues) >= 4

    def test_results_sorted_by_line_number(self):
        """Issues should be sorted by line number."""
        code = '''
while True:
    x = 1

password = "very_long_secret_password_123"

def bad(items=[]):
    pass
'''
        issues = self.analyzer.analyze(code, "python")
        line_numbers = [issue.line_number for issue in issues]
        assert line_numbers == sorted(line_numbers)

    def test_unsupported_language_returns_empty(self):
        """Unsupported languages should return empty, not error."""
        issues = self.analyzer.analyze("some code here", "rust")
        assert issues == []

    def test_empty_code_returns_empty(self):
        """Empty code string should produce no issues."""
        issues = self.analyzer.analyze("", "python")
        assert issues == []

    def test_performance_under_50ms(self):
        """Analysis of a 200-line file must complete in under 50ms.

        This is a hard spec requirement. We generate a 200-line file
        with a mix of clean code and some issues to test realistic
        performance.
        """
        # Generate a 200-line Python file with realistic content
        lines = []
        lines.append("import os")
        lines.append("import sys")
        lines.append("")
        lines.append("")

        # Add some functions with clean code (bulk of the file)
        for i in range(20):
            lines.append(f"def function_{i}(arg1, arg2):")
            lines.append(f'    """Process data for step {i}."""')
            lines.append(f"    result = arg1 + arg2")
            lines.append(f"    if result > 0:")
            lines.append(f"        return result")
            lines.append(f"    return 0")
            lines.append("")

        # Add a few deliberate issues
        lines.append('api_key = "sk-very-long-secret-key-value-here-12345678"')
        lines.append("")
        lines.append("def buggy(items=[]):")
        lines.append("    pass")
        lines.append("")

        # Pad to 200 lines
        while len(lines) < 200:
            lines.append(f"# Line {len(lines) + 1}")

        code = "\n".join(lines)
        assert len(lines) >= 200

        # Run analysis and measure time
        issues, elapsed_ms = self.analyzer.analyze_timed(code, "python")

        # Must complete in under 50ms
        assert elapsed_ms < 50, f"Analysis took {elapsed_ms:.1f}ms, exceeding 50ms limit"

        # Should still find the deliberately inserted issues
        assert len(issues) >= 2  # At least the secret and mutable default

    def test_deduplication(self):
        """Duplicate issues (same line + message) should be removed."""
        # This tests that if two rules somehow flag the same thing,
        # we don't show it twice
        code = '''
password = "AKIAIOSFODNN7EXAMPLE"
'''
        issues = self.analyzer.analyze(code, "python")
        # Check that no two issues have the same (line, message) pair
        seen = set()
        for issue in issues:
            key = (issue.line_number, issue.message)
            assert key not in seen, f"Duplicate issue: {key}"
            seen.add(key)
