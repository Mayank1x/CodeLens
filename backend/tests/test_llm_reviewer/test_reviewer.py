"""
Tests for the LLM Reviewer Orchestrator.

These tests use mocked LLM providers to verify that the orchestrator
correctly handles parsing, fallback on 429s, timeout propagation, and
deduplication against static issues without making actual network calls.
"""

import json
import pytest
from unittest.mock import Mock

from llm_reviewer.reviewer import LLMReviewer
from llm_reviewer.provider import LLMProvider, LLMRateLimitError, LLMAPIError
from static_analyzer.models import Issue


class MockProvider(LLMProvider):
    """A mock provider that returns predefined responses or raises exceptions."""
    def __init__(self, response=None, exception=None, delay=0):
        self.response = response
        self.exception = exception
        self.delay = delay
        self.call_count = 0

    def generate_review(self, prompt: str, timeout_seconds: int = 8) -> str:
        import time
        self.call_count += 1
        
        if self.delay > 0:
            time.sleep(self.delay)
            if self.delay > timeout_seconds:
                raise TimeoutError("Mock timeout")
                
        if self.exception:
            raise self.exception
        return self.response


class TestLLMReviewer:
    """Tests for the LLM orchestration layer."""

    def setup_method(self):
        # A valid JSON response representing what an LLM might return
        self.valid_json = json.dumps({
            "issues": [
                {
                    "line_number": 10,
                    "severity": "warning",
                    "category": "bug",
                    "message": "Potential race condition here.",
                    "suggestion": "Use a lock."
                }
            ]
        })
        
        self.static_issues = [
            Issue(5, "critical", "security", "Hardcoded secret", "Remove it")
        ]

    def test_successful_primary_call(self):
        """A successful call to the primary provider should parse correctly."""
        primary = MockProvider(response=self.valid_json)
        fallback = MockProvider(response="{}")
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=fallback)
        issues = reviewer.analyze("code", "python", self.static_issues)
        
        assert primary.call_count == 1
        assert fallback.call_count == 0
        
        # Should contain 1 static issue + 1 LLM issue
        assert len(issues) == 2
        assert issues[0].line_number == 5  # Static
        assert issues[1].line_number == 10 # LLM

    def test_fallback_on_rate_limit(self):
        """A 429 from the primary provider should trigger the fallback provider."""
        primary = MockProvider(exception=LLMRateLimitError("429 Too Many Requests"))
        fallback = MockProvider(response=self.valid_json)
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=fallback)
        issues = reviewer.analyze("code", "python", [])
        
        assert primary.call_count == 1
        assert fallback.call_count == 1
        assert len(issues) == 1
        assert issues[0].message == "Potential race condition here."

    def test_malformed_json_graceful_fail(self):
        """Malformed JSON from the LLM should fail gracefully and return static issues."""
        primary = MockProvider(response="This is not JSON at all")
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=None)
        issues = reviewer.analyze("code", "python", self.static_issues)
        
        # Should just return the static issues without crashing
        assert len(issues) == 1
        assert issues[0].line_number == 5

    def test_markdown_wrapped_json_handled(self):
        """JSON wrapped in markdown blocks (```json) should be parsed correctly."""
        markdown_json = f"```json\n{self.valid_json}\n```"
        primary = MockProvider(response=markdown_json)
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=None)
        issues = reviewer.analyze("code", "python", [])
        
        assert len(issues) == 1
        assert issues[0].line_number == 10

    def test_deduplication(self):
        """If the LLM returns an issue already found by static analysis, it's deduplicated."""
        # LLM returns the exact same issue as the static analyzer
        duplicate_json = json.dumps({
            "issues": [
                {
                    "line_number": 5,
                    "severity": "critical",
                    "category": "security",
                    "message": "Hardcoded secret",
                    "suggestion": "Different suggestion"
                }
            ]
        })
        primary = MockProvider(response=duplicate_json)
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=None)
        issues = reviewer.analyze("code", "python", self.static_issues)
        
        # Should only be 1 issue, not 2
        assert len(issues) == 1
        assert issues[0].line_number == 5

    def test_timeout_handled(self):
        """A timeout from the provider should be caught and fallback attempted/gracefully handled."""
        # Delay longer than the 8s default timeout
        primary = MockProvider(delay=10)
        
        reviewer = LLMReviewer(primary_provider=primary, fallback_provider=None)
        # Manually set a very short timeout for the test to run fast
        reviewer.timeout_seconds = 0.1 
        
        issues = reviewer.analyze("code", "python", self.static_issues)
        
        # Should gracefully return static issues
        assert len(issues) == 1
        assert issues[0].line_number == 5
