"""
Batch Model

Represents a multi-file analysis submission (e.g., from a ZIP upload or a GitHub repo scan).
A Batch groups multiple Review instances together and provides aggregated status and health score.
"""

import uuid
from datetime import datetime, timezone
from database import db


class Batch(db.Model):
    """A multi-file review submission."""

    __tablename__ = "batches"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id"),
        nullable=True, # Nullable to support Guest Mode (Phase 6)
    )
    source = db.Column(db.String(16), nullable=False) # 'zip' | 'github'
    source_url = db.Column(db.Text, nullable=True)    # Repo URL if source = 'github'
    
    status = db.Column(db.String(16), nullable=False, default="pending")
    total_files = db.Column(db.Integer, nullable=False, default=0)
    skipped_files = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    # One-to-many relationship with Reviews
    reviews = db.relationship(
        "Review",
        backref="batch",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_reviews=False):
        """Serialize to a dict for JSON responses."""
        data = {
            "id": self.id,
            "source": self.source,
            "source_url": self.source_url,
            "status": self.status,
            "total_files": self.total_files,
            "skipped_files": self.skipped_files,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

        if include_reviews:
            # Sort reviews by status/health or just return them
            all_reviews = self.reviews.all()
            data["reviews"] = [r.to_dict() for r in all_reviews]
            
            # Compute batch health score
            completed = [r for r in all_reviews if r.status == 'complete']
            if completed:
                total_score = sum(r.health_score for r in completed if r.health_score is not None)
                data["health_score"] = int(total_score / len(completed))
            else:
                data["health_score"] = None
                
        return data
