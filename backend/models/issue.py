"""
ReviewIssue Model

Represents a single issue found during a code review.
Named 'ReviewIssue' (not 'Issue') to avoid collision with the
static_analyzer.models.Issue dataclass used internally by the analyzers.

Each issue tracks its source ('static' or 'llm') so the frontend can
show which layer detected it — this is a great interview talking point
about the two-layer analysis architecture.
"""

import uuid
from database import db


class ReviewIssue(db.Model):
    """A single code issue persisted to the database after analysis."""

    __tablename__ = "issues"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    review_id = db.Column(
        db.String(36),
        db.ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 'static' or 'llm' — identifies which analysis layer found this issue
    source = db.Column(db.String(16), nullable=False)

    line_number = db.Column(db.Integer, nullable=True)
    severity = db.Column(db.String(16), nullable=False)  # critical | warning | info
    category = db.Column(db.String(16), nullable=False)  # bug | security | style | performance
    message = db.Column(db.Text, nullable=False)
    suggestion = db.Column(db.Text, nullable=True)

    def to_dict(self):
        """Serialize to a dict for JSON responses."""
        return {
            "id": self.id,
            "source": self.source,
            "line_number": self.line_number,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
        }
