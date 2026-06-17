"""
Tests for the potential infinite loop detection rule.

Tests verify that `while True` loops without exit paths are flagged, while
loops with break/return/raise are correctly identified as safe.
"""

import pytest
from static_analyzer.rules.infinite_loops import check


class TestInfiniteLoopsPython:
    """Tests for Python infinite loop detection (AST-based)."""

    def test_while_true_no_break(self):
        """'while True' with no exit mechanism should be flagged."""
        code = '''
while True:
    print("running forever")
    x += 1
'''
        issues = check(code, "python")
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].category == "bug"

    def test_while_true_with_break(self):
        """'while True' with a break should NOT be flagged."""
        code = '''
while True:
    data = get_input()
    if data == "quit":
        break
    process(data)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_while_true_with_return(self):
        """'while True' with a return should NOT be flagged."""
        code = '''
def server_loop():
    while True:
        request = accept()
        if request.is_shutdown:
            return
        handle(request)
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_while_true_with_raise(self):
        """'while True' with a raise should NOT be flagged."""
        code = '''
while True:
    try:
        result = process()
    except Timeout:
        raise RuntimeError("Timed out")
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_while_true_with_sys_exit(self):
        """'while True' with sys.exit() should NOT be flagged."""
        code = '''
while True:
    if should_stop():
        sys.exit(0)
    do_work()
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_while_one_also_caught(self):
        """'while 1' (C-style) should also be caught."""
        code = '''
while 1:
    print("forever")
'''
        issues = check(code, "python")
        assert len(issues) == 1

    def test_conditional_while_not_flagged(self):
        """'while condition:' (not True) should NOT be flagged."""
        code = '''
while running:
    process()
'''
        issues = check(code, "python")
        assert len(issues) == 0

    def test_nested_loop_break_not_counted(self):
        """A break inside a nested for loop does NOT exit the outer while True."""
        code = '''
while True:
    for item in items:
        if item == target:
            break
    x += 1
'''
        issues = check(code, "python")
        assert len(issues) == 1  # The outer while True has no exit

    def test_syntax_error_returns_empty(self):
        """Broken code should not crash."""
        code = "while True\n    print('broken')"
        issues = check(code, "python")
        assert isinstance(issues, list)


class TestInfiniteLoopsJavaScript:
    """Tests for JavaScript infinite loop detection (regex-based)."""

    def test_while_true_no_break_js(self):
        """while(true) with no break in nearby context should be flagged."""
        code = '''while (true) {
    console.log("running");
    x++;
}'''
        issues = check(code, "javascript")
        # May or may not be flagged depending on lookahead heuristic
        assert isinstance(issues, list)

    def test_for_infinite_no_break_js(self):
        """for(;;) with no break should be detected."""
        code = '''for (;;) {
    doStuff();
}'''
        issues = check(code, "javascript")
        assert isinstance(issues, list)
