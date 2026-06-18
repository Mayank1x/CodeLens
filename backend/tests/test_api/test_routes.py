"""
API Integration Tests

Tests the Flask application endpoints. Since we already unit-tested the
static analyzer and LLM orchestrator in isolation, these tests focus purely
on the HTTP layer: routing, JSON validation, status codes, and error handling.
"""

import json
import pytest
from app import create_app


@pytest.fixture
def client():
    """Create a Flask test client with dummy config."""
    # We pass a test config to ensure the API doesn't try to load
    # the real .env which might contain actual production keys.
    app = create_app({"TESTING": True})
    
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """Test the /health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"


def test_analyze_no_json(client):
    """Test that the API rejects non-JSON payloads."""
    response = client.post("/api/v1/analyze", data="This is not JSON")
    assert response.status_code == 400
    
    data = json.loads(response.data)
    assert "error" in data
    assert "JSON" in data["error"]


def test_analyze_no_code(client):
    """Test that the API rejects requests without the 'code' field."""
    response = client.post("/api/v1/analyze", json={"language": "python"})
    assert response.status_code == 400
    
    data = json.loads(response.data)
    assert "error" in data
    assert "No code provided" in data["error"]


def test_analyze_code_too_long(client):
    """Test that the API enforces the max code length limit."""
    # The limit is 150,000 chars. We send 150,001.
    long_code = "a" * 150001
    
    response = client.post("/api/v1/analyze", json={"code": long_code})
    assert response.status_code == 400
    
    data = json.loads(response.data)
    assert "error" in data
    assert "exceeds maximum allowed length" in data["error"]


def test_analyze_successful_static(client, monkeypatch):
    """Test a successful analysis run (static only).
    
    We mock the LLMReviewer to ensure we don't accidentally make real network
    calls if the host machine has API keys set in the environment.
    """
    # Mock the LLM Reviewer to return exactly what it received (no extra issues)
    from llm_reviewer.reviewer import LLMReviewer
    def mock_analyze(self, code, language, static_issues):
        return static_issues
        
    monkeypatch.setattr(LLMReviewer, "analyze", mock_analyze)
    
    # A simple buggy Python snippet
    code = "password = 'secret123'"
    
    response = client.post("/api/v1/analyze", json={
        "code": code,
        "language": "python"
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    assert data["status"] == "success"
    assert data["language"] == "python"
    assert "analysis_time_ms" in data
    
    # It should have found the hardcoded secret and the unused variable
    assert data["total_issues"] == 2
    assert len(data["issues"]) == 2
    
    # Verify the structure of the returned issues
    issue = data["issues"][0]
    assert "line_number" in issue
    assert "severity" in issue
    assert "category" in issue
    assert "message" in issue
    assert "suggestion" in issue
