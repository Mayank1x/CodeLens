"""
Analyzer — The orchestrator that runs all static analysis rules.

This is the main entry point for the static analysis engine. It takes
raw source code and a language identifier, runs all registered rules,
and returns a deduplicated, sorted list of Issue objects.

Design choice: The analyzer doesn't know about individual rules' internals.
It imports the ALL_RULES list from the rules package and calls each rule's
check() function. This means adding a new rule only requires:
1. Creating a new module in rules/
2. Adding it to the ALL_RULES list in rules/__init__.py
No changes to this file are needed.
"""

import time
from .models import Issue
from .rules import ALL_RULES


# Mapping from file extensions to language identifiers.
# Used by the CLI to auto-detect language from file names.
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",  # TypeScript is close enough for our regex rules
    ".tsx": "javascript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",  # C is close enough to C++ for our pattern matching
    ".h": "cpp",
    ".hpp": "cpp",
}

# Supported languages for the language dropdown in the frontend
SUPPORTED_LANGUAGES = ["python", "javascript", "java", "cpp"]


class StaticAnalyzer:
    """Runs all registered static analysis rules against source code.

    Usage:
        analyzer = StaticAnalyzer()
        issues = analyzer.analyze("def foo(x=[]):\n    pass", "python")
        for issue in issues:
            print(f"Line {issue.line_number}: [{issue.severity}] {issue.message}")
    """

    def __init__(self):
        """Initialize with all registered rules.

        We store rules at init time (not at call time) so the cost of
        importing rule modules is paid once, not on every analyze() call.
        """
        self.rules = ALL_RULES

    def analyze(self, code: str, language: str) -> list[Issue]:
        """Run all analysis rules and return a sorted, deduplicated list of issues.

        Args:
            code: The source code to analyze (as a string).
            language: The programming language ('python', 'javascript', 'java', 'cpp').

        Returns:
            A list of Issue objects, sorted by line number then severity.
            Duplicates (same line + same message) are removed.
        """
        if language not in SUPPORTED_LANGUAGES:
            # Return empty rather than raising — the caller might want to
            # still run the LLM layer on unsupported languages
            return []

        all_issues: list[Issue] = []

        for rule_module in self.rules:
            try:
                issues = rule_module.check(code, language)
                all_issues.extend(issues)
            except Exception as e:
                # If a single rule crashes, we don't want it to take down
                # the entire analysis. Log the error and continue with
                # the other rules. This is a resilience pattern.
                print(
                    f"Warning: Rule '{rule_module.__name__}' raised an error: {e}. "
                    f"Skipping this rule."
                )

        # Deduplicate issues with the same line number and message
        # (can happen when multiple rules detect the same problem)
        all_issues = self._deduplicate(all_issues)

        # Sort by line number first, then by severity (critical > warning > info)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        all_issues.sort(
            key=lambda issue: (issue.line_number, severity_order.get(issue.severity, 3))
        )

        return all_issues

    def analyze_timed(self, code: str, language: str) -> tuple[list[Issue], float]:
        """Run analysis and also return the elapsed time in milliseconds.

        Useful for performance monitoring and the spec's < 50ms requirement.
        """
        start = time.perf_counter()
        issues = self.analyze(code, language)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return issues, elapsed_ms

    @staticmethod
    def _deduplicate(issues: list[Issue]) -> list[Issue]:
        """Remove duplicate issues (same line number and message).

        We use (line_number, message) as the deduplication key because
        two different rules might flag the same line for the same reason.
        """
        seen = set()
        unique = []
        for issue in issues:
            key = (issue.line_number, issue.message)
            if key not in seen:
                seen.add(key)
                unique.append(issue)
        return unique
