"""
Review Model

Represents a code review request submitted by a user.
The review goes through a lifecycle: pending → processing → complete/failed.
This status-based design enables async processing — the API returns
immediately with a review_id, and the client polls until status is 'complete'.
"""

import uuid
from datetime import datetime, timezone
from database import db


class Review(db.Model):
    """A single code review request and its lifecycle status."""

    __tablename__ = "reviews"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=False,
    )
    language = db.Column(db.String(32), nullable=False)
    code_snippet = db.Column(db.Text, nullable=False)

    # Status lifecycle: pending → processing → complete | failed
    # Using a string column rather than a Postgres ENUM so we can add
    # new statuses without a database migration.
    status = db.Column(db.String(16), nullable=False, default="pending")

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationship to issues — cascade delete so cleaning up a review
    # automatically removes its issues (no orphaned data)
    issues = db.relationship(
        "ReviewIssue",
        backref="review",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_issues=False):
        """Serialize to a dict for JSON responses.

        Args:
            include_issues: If True, include the full list of issues.
                           Set to False for list/history views (lighter payload).
        """
        data = {
            "id": self.id,
            "language": self.language,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "issue_count": self.issues.count(),
        }

        if include_issues:
            data["code"] = self.code_snippet
            data["issues"] = [issue.to_dict() for issue in self.issues.all()]

        return data
