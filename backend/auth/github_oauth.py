"""
GitHub OAuth2 Helper

Handles the two-step OAuth2 exchange:
1. Frontend redirects user to GitHub's authorization URL
2. GitHub redirects back with a temporary `code`
3. This module exchanges that code for an access token
4. Then fetches the user's GitHub profile with that token

Design decision: We use raw `requests` calls instead of a library like
Flask-Dance because the OAuth2 code exchange is just two HTTP calls,
and keeping it explicit makes the flow easy to explain in interviews.
"""

import os
import requests


# GitHub OAuth2 endpoints
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def exchange_code_for_token(code: str) -> str:
    """Exchange the temporary OAuth code for a GitHub access token.

    Args:
        code: The authorization code from GitHub's redirect.

    Returns:
        The access token string.

    Raises:
        ValueError: If the exchange fails (invalid code, expired, etc.)
    """
    client_id = os.environ.get("GITHUB_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set in environment variables."
        )

    response = requests.post(
        GITHUB_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        headers={
            # Request JSON response instead of the default URL-encoded format
            "Accept": "application/json",
        },
        timeout=10,
    )

    data = response.json()

    if "access_token" not in data:
        error_desc = data.get("error_description", "Unknown error")
        raise ValueError(f"GitHub OAuth failed: {error_desc}")

    return data["access_token"]


def get_github_user(access_token: str) -> dict:
    """Fetch the authenticated user's GitHub profile.

    Args:
        access_token: A valid GitHub OAuth access token.

    Returns:
        A dict with keys: 'id' (int), 'login' (str), 'avatar_url' (str).

    Raises:
        ValueError: If the GitHub API call fails.
    """
    response = requests.get(
        GITHUB_USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise ValueError(f"GitHub API error: {response.status_code} {response.text}")

    data = response.json()

    return {
        "id": str(data["id"]),       # Convert to string for consistent storage
        "login": data["login"],
        "avatar_url": data.get("avatar_url", ""),
    }
