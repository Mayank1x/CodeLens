"""
Background Review Worker

This module contains the function that runs code analysis in a background
thread. When a user submits code via POST /api/review, the API immediately
returns a review_id and dispatches this worker to do the actual analysis.

Design choice: ThreadPoolExecutor over Celery because:
1. No additional infrastructure (Redis/RabbitMQ) required
2. Perfectly adequate for the expected load of a portfolio project
3. Simpler deployment on free-tier hosting (no worker process needed)
In production at scale, you'd migrate to Celery + Redis for proper
job queue semantics (retries, priority queues, dead letter queues, etc.)

IMPORTANT: This function runs in a separate thread but needs access to
the Flask app context for database operations. We pass the `app` object
and use `app.app_context()` to create a fresh context for the thread.
"""

from datetime import datetime, timezone
from database import db
from models.review import Review
from models.issue import ReviewIssue
from static_analyzer.analyzer import StaticAnalyzer
from llm_reviewer.reviewer import LLMReviewer


def process_review(app, review_id: str):
    """Run static + LLM analysis for a review and persist the results.

    This function is meant to be submitted to a ThreadPoolExecutor.
    It wraps all work in a try/except so a failed review gets marked
    as 'failed' rather than silently disappearing.

    Args:
        app: The Flask application instance (needed for app context).
        review_id: The UUID of the Review record to process.
    """
    with app.app_context():
        review = db.session.get(Review, review_id)

        if not review:
            print(f"Error: Review {review_id} not found in database.")
            return

        try:
            # Mark as processing so the polling endpoint can show progress
            review.status = "processing"
            db.session.commit()

            code = review.code_snippet
            language = review.language

            # Step 1: Run static analysis
            static_analyzer = StaticAnalyzer()
            static_issues, static_ms = static_analyzer.analyze_timed(code, language)

            # Save static issues to the database
            for issue in static_issues:
                db_issue = ReviewIssue(
                    review_id=review_id,
                    source="static",
                    line_number=issue.line_number,
                    severity=issue.severity,
                    category=issue.category,
                    message=issue.message,
                    suggestion=issue.suggestion,
                )
                db.session.add(db_issue)

            # Step 2: Run LLM analysis (gracefully falls back to static-only)
            llm_reviewer = LLMReviewer()
            all_issues = llm_reviewer.analyze(code, language, static_issues)

            # Find issues that the LLM added (not in static_issues)
            # We identify LLM-only issues by checking which ones weren't
            # in the original static_issues list (by message + line_number)
            static_keys = {
                (issue.line_number, issue.message) for issue in static_issues
            }

            for issue in all_issues:
                key = (issue.line_number, issue.message)
                if key not in static_keys:
                    # This issue came from the LLM
                    db_issue = ReviewIssue(
                        review_id=review_id,
                        source="llm",
                        line_number=issue.line_number,
                        severity=issue.severity,
                        category=issue.category,
                        message=issue.message,
                        suggestion=issue.suggestion,
                    )
                    db.session.add(db_issue)

            # Mark review as complete
            review.status = "complete"
            review.completed_at = datetime.now(timezone.utc)
            db.session.commit()

            total_issues = ReviewIssue.query.filter_by(review_id=review_id).count()
            print(f"Review {review_id} completed: {total_issues} issues found ({static_ms:.1f}ms static analysis)")

        except Exception as e:
            # Mark the review as failed so the client knows something went wrong
            # rather than polling forever
            print(f"Review {review_id} failed: {e}")
            try:
                review.status = "failed"
                db.session.commit()
            except Exception:
                # If even the status update fails (e.g., DB connection lost),
                # there's nothing more we can do
                db.session.rollback()
                print(f"Could not update review {review_id} status to 'failed'.")
