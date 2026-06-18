"""
JWT Token Utilities

Creates and validates JSON Web Tokens (JWTs) for session management.

Design decisions:
- HS256 algorithm: Symmetric signing is appropriate here because only
  our backend creates AND validates tokens (no third-party verification).
- 24-hour expiry: Long enough for a demo session, short enough to limit
  exposure if a token leaks. In production, you'd use refresh tokens.
- We store user_id in the 'sub' (subject) claim following JWT best practices.
"""

import os
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


def create_token(user_id: str) -> str:
    """Create a signed JWT containing the user's ID.

    Args:
        user_id: The UUID of the authenticated user.

    Returns:
        A signed JWT string.
    """
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,                                    # Subject: who this token is for
        "iat": now,                                        # Issued At: when the token was created
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),  # Expiration: when it becomes invalid
    }

    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def decode_token(token: str) -> str:
    """Validate and decode a JWT, returning the user_id.

    Args:
        token: The JWT string from the Authorization header.

    Returns:
        The user_id (UUID string) from the token's 'sub' claim.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is malformed or tampered with.
    """
    payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
    return payload["sub"]
