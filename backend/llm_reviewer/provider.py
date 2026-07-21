"""
LLM Provider Abstraction

This module defines the Strategy pattern for interacting with LLMs.
By abstracting the provider behind an interface, the rest of the application
doesn't need to care whether it's talking to Gemini, Groq, or OpenAI.

Design decision: We use the requests library for the Groq API rather than
the official SDK to minimize heavy dependencies and show we understand
how to interact with standard REST APIs. We use the google-genai SDK for
Gemini because its REST API for structured output is more complex.
"""

import os
import json
import requests
from abc import ABC, abstractmethod
from google import genai
from google.genai import types


class LLMRateLimitError(Exception):
    """Raised when an LLM provider returns a 429 Too Many Requests status."""
    pass


class LLMAPIError(Exception):
    """Raised when an LLM provider returns a general API error."""
    pass


class LLMProvider(ABC):
    """Abstract Base Class for LLM providers."""

    @abstractmethod
    def generate_review(self, prompt: str, timeout_seconds: int = 8) -> str:
        """Send the prompt to the LLM and return the raw text response.

        Args:
            prompt: The full instruction prompt including the code.
            timeout_seconds: Maximum time to wait for a response.

        Returns:
            The raw text string returned by the LLM (expected to be JSON).

        Raises:
            LLMRateLimitError: If the provider's rate limit is exceeded.
            LLMAPIError: If the provider returns a non-429 error.
            TimeoutError: If the request takes longer than timeout_seconds.
        """
        pass


class GeminiProvider(LLMProvider):
    """Implementation for Google's Gemini API (gemini-2.5-flash)."""

    def __init__(self, api_key: str = None):
        # Fall back to environment variable if not explicitly provided
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        self.client = genai.Client(api_key=self.api_key, http_options={'timeout': 30000})
        # We explicitly use Flash because it's fast and has a generous free tier
        self.model_name = "gemini-2.5-flash"

    def generate_review(self, prompt: str, timeout_seconds: int = 8) -> str:
        try:
            # We use the config object to enforce JSON output. This prevents
            # the LLM from wrapping the JSON in markdown code blocks like ```json
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2, # Low temperature for more deterministic, analytical output
            )

            # Note: The google-genai SDK doesn't natively expose a timeout parameter
            # in its high-level generate_content call yet, but we will handle the
            # timeout at the orchestrator level using a background thread/future.
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return response.text

        except Exception as e:
            error_str = str(e).lower()
            # Catch 429s specifically so the orchestrator knows to trigger the fallback
            if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                raise LLMRateLimitError(f"Gemini rate limit exceeded: {e}")
            raise LLMAPIError(f"Gemini API error: {e}")


class GroqProvider(LLMProvider):
    """Implementation for Groq's fast inference API (llama-3.3-70b-versatile)."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model_name = "llama-3.3-70b-versatile"

    def generate_review(self, prompt: str, timeout_seconds: int = 8) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Groq uses the OpenAI-compatible chat completions endpoint
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert software engineer performing a code review. You must respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds
            )

            if response.status_code == 429:
                raise LLMRateLimitError("Groq rate limit exceeded.")

            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]

        except requests.exceptions.Timeout:
            raise TimeoutError(f"Groq API timed out after {timeout_seconds}s")
        except requests.exceptions.RequestException as e:
            # We already caught 429s above, this catches 401s, 500s, etc.
            raise LLMAPIError(f"Groq API error: {e}")
