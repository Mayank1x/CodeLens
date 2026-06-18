"""
User Model

Represents a user who authenticated via GitHub OAuth.
We store minimal profile info (github_id, username, avatar_url)
to avoid re-fetching it from GitHub on every request.
"""

import uuid
from datetime import datetime, timezone
from database import db


class User(db.Model):
    """A registered user, identified by their GitHub account."""

    __tablename__ = "users"

    # UUIDs as primary keys instead of auto-increment integers because:
    # 1. They don't leak information about total user count
    # 2. They're safe to expose in URLs and API responses
    # 3. They can be generated client-side if ever needed
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    github_id = db.Column(db.String(64), unique=True, nullable=False)
    username = db.Column(db.String(128), nullable=False)
    avatar_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to reviews — enables user.reviews to get all reviews
    reviews = db.relationship("Review", backref="user", lazy="dynamic")

    def to_dict(self):
        """Serialize to a dict for JSON responses."""
        return {
            "id": self.id,
            "username": self.username,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
