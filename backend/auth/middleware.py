"""
Authentication Middleware

Provides the @require_auth decorator that protects API routes.
It extracts the JWT from the Authorization header, validates it,
and attaches the current user's ID to Flask's `g` object.

Development mode: When SKIP_AUTH=true is set, the decorator creates
or reuses a default test user, so you can test endpoints without
going through the GitHub OAuth flow. This is clearly documented
and must NEVER be enabled in production.
"""

import os
import uuid
from functools import wraps
from flask import request, jsonify, g

from auth.jwt_utils import decode_token
from database import db


def require_auth(f):
    """Decorator that enforces JWT authentication on a route.

    On success, sets:
        g.current_user_id — the UUID of the authenticated user

    On failure, returns a 401 JSON error response.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # --- Dev mode shortcut ---
        # If SKIP_AUTH is true, use a default test user instead of requiring
        # a real JWT. This makes local development much faster.
        if os.environ.get("SKIP_AUTH", "").lower() == "true":
            g.current_user_id = _get_or_create_dev_user()
            g.is_guest = False
            g.guest_session_id = None
            return f(*args, **kwargs)

        # --- Production auth flow ---
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Missing Authorization header."}), 401

        # Expected format: "Bearer <token>"
        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Invalid Authorization header format. Expected: Bearer <token>"}), 401

        token = parts[1]

        try:
            payload = decode_token(token)
            
            if payload.get("is_guest"):
                g.current_user_id = None
                g.is_guest = True
                # Guest session ID ties this guest's reviews to their specific session
                g.guest_session_id = payload.get("guest_session_id")
            else:
                g.current_user_id = payload.get("sub")
                g.is_guest = False
                g.guest_session_id = None
                
        except Exception as e:
            # Catches ExpiredSignatureError, InvalidTokenError, etc.
            return jsonify({"error": f"Invalid or expired token: {str(e)}"}), 401

        return f(*args, **kwargs)

    return decorated


def _get_or_create_dev_user() -> str:
    """Get or create a default development user.

    This is only used when SKIP_AUTH=true. It creates a persistent
    test user in the database so reviews are properly associated.
    """
    from models.user import User

    dev_github_id = "dev-user-00000"
    dev_user = User.query.filter_by(github_id=dev_github_id).first()

    if not dev_user:
        dev_user = User(
            id=str(uuid.uuid4()),
            github_id=dev_github_id,
            username="dev-user",
            avatar_url="https://github.com/ghost.png",
        )
        db.session.add(dev_user)
        db.session.commit()

    return dev_user.id
