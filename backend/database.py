"""
Database Configuration — Flask-SQLAlchemy Setup

This module initializes the SQLAlchemy ORM instance that all models share.
We keep it separate from app.py to avoid circular imports: models import `db`
from here, and app.py imports `db` to bind it to the Flask app.

Design choice: SQLAlchemy over raw SQL because it gives us model-level
validation, relationship management, and query building while still
allowing raw SQL if needed. For a project this size, the ORM overhead
is negligible and the code clarity gain is significant.
"""

import os
from flask_sqlalchemy import SQLAlchemy

# Initialize without binding to an app yet — we'll call db.init_app(app)
# in the application factory. This is the "application factory" pattern
# recommended by Flask-SQLAlchemy's documentation.
db = SQLAlchemy()


def init_db(app):
    """Bind the SQLAlchemy instance to the Flask app and create tables.

    Called once during app initialization. In production, you'd use
    Flask-Migrate (Alembic) for schema migrations, but for v1 we use
    create_all() which is simpler and sufficient.
    """
    db.init_app(app)

    with app.app_context():
        # Import all models so SQLAlchemy knows about them before create_all()
        from models.user import User      # noqa: F401
        from models.batch import Batch    # noqa: F401
        from models.review import Review  # noqa: F401
        from models.issue import ReviewIssue  # noqa: F401

        db.create_all()
