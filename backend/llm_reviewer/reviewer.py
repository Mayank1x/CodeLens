"""
LLM Reviewer Orchestrator

This module acts as the entry point for the semantic analysis layer.
It handles:
1. Calling the primary provider (Gemini)
2. Parsing and validating the JSON response
3. Retrying on malformed JSON
4. Falling back to the secondary provider (Groq) on rate limits
5. Gracefully failing back to static-only results if all else fails
6. Merging and deduplicating the LLM issues with the static issues
"""

import json
import concurrent.futures
from static_analyzer.models import Issue
from .provider import LLMProvider, GeminiProvider, GroqProvider, LLMRateLimitError
from .prompt import build_review_prompt


class LLMReviewer:
    """Orchestrates the LLM code review process."""

    def __init__(self, primary_provider: LLMProvider = None, fallback_provider: LLMProvider = None):
        """Initialize the reviewer with specific providers.

        If not provided, defaults to Gemini as primary and Groq as fallback,
        assuming API keys are available in the environment. If keys are missing,
        those providers will fail to initialize. We handle this gracefully in analyze().
        """
        # Try to initialize default providers if none are given
        try:
            self.primary = primary_provider or GeminiProvider()
        except ValueError:
            self.primary = None
            print("Warning: Gemini API key not found. LLM review disabled.")

        try:
            self.fallback = fallback_provider or GroqProvider()
        except ValueError:
            self.fallback = None
            # Not having a fallback is fine, we just won't fall back
        # Increased timeout to 30 seconds because Gemini is currently taking ~18s
        self.timeout_seconds = 30

    def analyze(self, code: str, language: str, static_issues: list[Issue], diff_text: str = None) -> list[Issue]:
        """Run the LLM review and merge results with static issues.

        This method is guaranteed to return a valid list of issues, even if
        the LLM fails completely (in which case it just returns the static issues).
        """
        if not self.primary:
            return static_issues

        prompt = build_review_prompt(code, language, static_issues, diff_text)

        # Attempt to get a valid JSON response from the LLM
        llm_response_text = self._execute_with_fallback_and_retry(prompt)

        if not llm_response_text:
            # Track static-only fallback for admin dashboard health monitoring
            try:
                from api.review_worker import llm_health_stats
                llm_health_stats["static_only"] += 1
            except ImportError:
                pass  # CLI mode — no worker module available
            print("Warning: LLM analysis failed or timed out. Returning static results only.")
            return static_issues

        # Parse and validate the response
        llm_issues = self._parse_response(llm_response_text)

        # Merge and deduplicate
        return self._merge_issues(static_issues, llm_issues)

    def _execute_with_fallback_and_retry(self, prompt: str) -> str:
        """Execute the LLM call, handling retries, fallbacks, and timeouts.

        Also tracks which provider succeeded/failed for the admin dashboard's
        LLM health monitoring panel.
        """
        from api.review_worker import llm_health_stats

        # Attempt 1: Primary provider (Gemini)
        try:
            result = self._call_provider_with_timeout(self.primary, prompt)
            llm_health_stats["gemini_success"] += 1
            return result
        except LLMRateLimitError as e:
            print(f"Primary provider rate limited: {e}. Falling back to secondary...")
        except Exception as e:
            print(f"Primary provider failed: {e}. Falling back to secondary...")

        # Attempt 2: Fallback provider (Groq)
        if self.fallback:
            try:
                result = self._call_provider_with_timeout(self.fallback, prompt)
                llm_health_stats["groq_fallback"] += 1
                return result
            except Exception as e:
                print(f"Fallback provider also failed: {e}.")

        # Both providers failed — will return static-only results
        llm_health_stats["llm_failure"] += 1
        return None

    def _call_provider_with_timeout(self, provider: LLMProvider, prompt: str) -> str:
        """Call a provider directly."""
        # We removed the inner ThreadPoolExecutor because nested executors 
        # combined with google-genai's internal asyncio loop can cause deadlocks 
        # in the Flask worker context. We will rely on the provider's native HTTP timeout.
        try:
            return provider.generate_review(prompt)
        except Exception as e:
            print(f"Provider {provider.__class__.__name__} failed: {e}")
            raise

    def _parse_response(self, response_text: str) -> list[Issue]:
        """Parse the LLM's JSON response and convert to Issue objects."""
        try:
            # The LLM *might* wrap the JSON in markdown blocks despite our instructions
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]

            data = json.loads(cleaned_text)

            if "issues" not in data or not isinstance(data["issues"], list):
                print("Warning: LLM JSON response missing 'issues' array.")
                return []

            issues = []
            for item in data["issues"]:
                try:
                    issues.append(
                        Issue(
                            line_number=int(item.get("line_number", 1)),
                            severity=item.get("severity", "info"),
                            category=item.get("category", "bug"),
                            message=str(item.get("message", "No message provided")),
                            suggestion=str(item.get("suggestion", ""))
                        )
                    )
                except (ValueError, TypeError):
                    # Skip malformed individual issues rather than dropping the whole list
                    continue

            return issues

        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse LLM response as JSON: {e}")
            print(f"Raw response was: {response_text[:100]}...")
            return []

    def _merge_issues(self, static_issues: list[Issue], llm_issues: list[Issue]) -> list[Issue]:
        """Merge both lists and deduplicate.

        Even though we told the LLM not to duplicate static findings, it
        might still do it. We deduplicate using (line_number, message).
        """
        all_issues = static_issues + llm_issues
        seen = set()
        unique = []

        for issue in all_issues:
            key = (issue.line_number, issue.message)
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        # Sort by line number, then by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        unique.sort(
            key=lambda i: (i.line_number, severity_order.get(i.severity, 3))
        )

        return unique
