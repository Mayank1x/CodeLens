"""
API Integration Tests — Phase 3

Tests all Flask API endpoints with proper mocking of external dependencies
(GitHub OAuth, LLM providers, database). Since we already unit-tested the
static analyzer and LLM orchestrator in isolation, these tests focus on:
- HTTP layer: routing, status codes, JSON structure
- Auth middleware: JWT validation, SKIP_AUTH mode
- Input validation: code length/line limits
- Async review flow: submit → poll → complete
- History and stats endpoints
"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    """Create a Flask app configured for testing.

    Uses DATABASE_URL from the environment if available (for tests that need
    PostgreSQL, e.g. inside docker-compose). Otherwise falls back to SQLite
    in-memory, which is sufficient for unit-level API tests.
    """
    import os
    os.environ["SKIP_AUTH"] = "true"
    os.environ["JWT_SECRET"] = "test-secret"

    from app import create_app
    from database import db

    # Use PostgreSQL if DATABASE_URL is set, otherwise SQLite in-memory
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        test_db_url = db_url.rsplit("/", 1)[0] + "/codelens_test"
    else:
        test_db_url = "sqlite:///:memory:"

    test_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": test_db_url,
    })

    # Create all tables fresh for each test session
    with test_app.app_context():
        db.create_all()

    yield test_app

    # Cleanup: drop all tables after tests
    with test_app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    with app.test_client() as client:
        yield client


# =============================================================================
# HEALTH CHECK
# =============================================================================

def test_health_check(client):
    """Test the /health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"


# =============================================================================
# AUTH ENDPOINT
# =============================================================================

@patch("api.routes.get_github_user")
@patch("api.routes.exchange_code_for_token")
def test_github_auth_callback(mock_exchange, mock_get_user, client):
    """Test the GitHub OAuth callback creates a user and returns a JWT."""
    mock_exchange.return_value = "fake_access_token"
    mock_get_user.return_value = {
        "id": "12345",
        "login": "testuser",
        "avatar_url": "https://github.com/testuser.png",
    }

    response = client.post("/api/auth/github/callback", json={"code": "test_code"})
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "token" in data
    assert "user" in data
    assert data["user"]["username"] == "testuser"


def test_github_auth_missing_code(client):
    """Test that the OAuth callback rejects requests without a code."""
    response = client.post("/api/auth/github/callback", json={})
    assert response.status_code == 400

    data = json.loads(response.data)
    assert "error" in data


# =============================================================================
# REVIEW SUBMISSION
# =============================================================================

@patch("api.review_worker.LLMReviewer")
def test_submit_review(mock_llm_class, client):
    """Test submitting code for review returns a review_id immediately."""
    # Mock the LLM reviewer so it doesn't make real API calls
    mock_instance = MagicMock()
    mock_instance.analyze.return_value = []
    mock_llm_class.return_value = mock_instance

    response = client.post("/api/review", json={
        "code": "password = 'secret123'",
        "language": "python",
    })
    assert response.status_code == 202

    data = json.loads(response.data)
    assert "review_id" in data
    assert data["status"] == "pending"


def test_submit_review_no_code(client):
    """Test that submitting without code returns 400."""
    response = client.post("/api/review", json={"language": "python"})
    assert response.status_code == 400

    data = json.loads(response.data)
    assert "error" in data
    assert "No code" in data["error"]


def test_submit_review_no_json(client):
    """Test that non-JSON requests are rejected."""
    response = client.post("/api/review", data="not json")
    assert response.status_code == 400


def test_submit_review_code_too_long(client):
    """Test that code exceeding 500KB is rejected."""
    # 500KB + 1 byte
    long_code = "a" * (500 * 1024 + 1)
    response = client.post("/api/review", json={"code": long_code})
    assert response.status_code == 400

    data = json.loads(response.data)
    assert "exceeds" in data["error"]


def test_submit_review_too_many_lines(client):
    """Test that code exceeding 5000 lines is rejected."""
    # 5001 lines
    many_lines = "\n".join(["x = 1"] * 5001)
    response = client.post("/api/review", json={"code": many_lines})
    assert response.status_code == 400

    data = json.loads(response.data)
    assert "line count" in data["error"]


# =============================================================================
# REVIEW POLLING
# =============================================================================

@patch("api.review_worker.LLMReviewer")
def test_get_review_status(mock_llm_class, client):
    """Test polling for a review's status."""
    mock_instance = MagicMock()
    mock_instance.analyze.return_value = []
    mock_llm_class.return_value = mock_instance

    # Submit a review first
    submit_response = client.post("/api/review", json={
        "code": "x = 1",
        "language": "python",
    })
    review_id = json.loads(submit_response.data)["review_id"]

    # Poll for status; keep polling until terminal state so teardown doesn't
    # race with the background worker still writing to the DB.
    deadline = time.time() + 5
    data = None
    while time.time() < deadline:
        response = client.get(f"/api/review/{review_id}")
        assert response.status_code == 200
        data = json.loads(response.data)
        if data["status"] in ["complete", "failed"]:
            break
        time.sleep(0.1)

    assert data is not None
    assert data["id"] == review_id
    assert data["status"] in ["complete", "failed"]


def test_get_review_not_found(client):
    """Test polling for a non-existent review returns 404."""
    response = client.get("/api/review/nonexistent-id")
    assert response.status_code == 404


# =============================================================================
# HISTORY ENDPOINT
# =============================================================================

@patch("api.review_worker.LLMReviewer")
def test_get_history(mock_llm_class, client):
    """Test the history endpoint returns paginated results.

    We submit a single review and wait for the background worker to finish.
    Multiple concurrent reviews can crash SQLite in-memory (single-thread).
    """
    mock_instance = MagicMock()
    mock_instance.analyze.return_value = []
    mock_llm_class.return_value = mock_instance

    # Submit a single review
    client.post("/api/review", json={
        "code": "x = 1",
        "language": "python",
    })

    # Wait for background worker to finish
    time.sleep(3)

    # Get history
    response = client.get("/api/history")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "reviews" in data
    assert "page" in data
    assert "total" in data
    assert data["total"] >= 1


def test_get_history_pagination(client):
    """Test history pagination parameters."""
    response = client.get("/api/history?page=1&per_page=5")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data["page"] == 1
    assert data["per_page"] == 5


# =============================================================================
# STATS ENDPOINT
# =============================================================================

def test_get_stats_empty(client):
    """Test stats for a user with no reviews."""
    response = client.get("/api/stats")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data["total_reviews"] == 0
    assert data["average_issues_per_review"] == 0
    assert data["category_breakdown"] == {}
    assert data["severity_breakdown"] == {}
