"""
JWT Token Utilities

Creates and validates JSON Web Tokens (JWTs) for session management.

Design decisions:
- HS256 algorithm: Symmetric signing is appropriate here because only
  our backend creates AND validates tokens (no third-party verification).
- 24-hour expiry: Long enough for a demo session, short enough to limit
  exposure if a token leaks. In production, you'd use refresh tokens.
- We store user_id in the 'sub' (subject) claim following JWT best practices.
- Guest tokens include a unique guest_session_id so we can tie guest reviews
  to a specific anonymous session without creating a database user record.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
import jwt  # PyJWT library


# Token lifetime — 24 hours is a good balance for a demo project
TOKEN_EXPIRY_HOURS = 24


def _get_secret() -> str:
    """Get the JWT signing secret from environment variables."""
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise ValueError("JWT_SECRET environment variable is not set.")
    return secret


def create_token(user_id: str = None, is_guest: bool = False) -> str:
    """Create a signed JWT containing the user's ID or a guest flag.

    Args:
        user_id: The UUID of the authenticated user (None for guests).
        is_guest: Boolean indicating if this is a guest session.

    Returns:
        A signed JWT string.
    """
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id if user_id else "guest",
        "is_guest": is_guest,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }

    # Each guest session gets a unique ID so we can track review ownership
    # without creating a real database user record.
    if is_guest:
        payload["guest_session_id"] = str(uuid.uuid4())

    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def decode_token(token: str) -> dict:
    """Validate and decode a JWT, returning the payload.

    Args:
        token: The JWT string from the Authorization header.

    Returns:
        A dictionary containing the token claims (sub, is_guest, guest_session_id, etc.)

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is malformed or tampered with.
    """
    return jwt.decode(token, _get_secret(), algorithms=["HS256"])
