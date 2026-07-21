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
from models.batch import Batch
from static_analyzer.analyzer import StaticAnalyzer
from llm_reviewer.reviewer import LLMReviewer
from llm_reviewer.provider import LLMRateLimitError
import shutil
import difflib

# In-memory counters for LLM provider health tracking.
# The admin dashboard reads these to show Gemini success rate,
# Groq fallback frequency, and total failures.
# In production, you'd persist these to the database or a metrics service.
llm_health_stats = {
    "gemini_success": 0,
    "groq_fallback": 0,
    "llm_failure": 0,
    "static_only": 0,
}

def compute_health_score(issues):
    """Compute a health score based on severities.
    Start at 100, subtract 15 for critical, 5 for warning, 1 for info.
    """
    score = 100
    for issue in issues:
        if issue.severity == "critical":
            score -= 15
        elif issue.severity == "warning":
            score -= 5
        elif issue.severity == "info":
            score -= 1
    return max(0, score)


def process_review(app, review_id: str, previous_review_id: str = None):
    """Run static + LLM analysis for a review and persist the results.

    This function is meant to be submitted to a ThreadPoolExecutor.
    It wraps all work in a try/except so a failed review gets marked
    as 'failed' rather than silently disappearing.

    Args:
        app: The Flask application instance (needed for app context).
        review_id: The UUID of the Review record to process.
        previous_review_id: Optional. UUID of the previous review to generate a diff.
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
                
            # Step 1.5: Compute Diff (if previous_review_id provided)
            diff_text = None
            if previous_review_id:
                prev_review = db.session.get(Review, previous_review_id)
                if prev_review and prev_review.code_snippet:
                    # Calculate unified diff
                    prev_lines = prev_review.code_snippet.splitlines(keepends=True)
                    curr_lines = code.splitlines(keepends=True)
                    diff = difflib.unified_diff(
                        prev_lines, curr_lines,
                        fromfile="previous_version", tofile="current_version",
                        n=3
                    )
                    diff_text = "".join(diff)

            # Step 2: Run LLM analysis (gracefully falls back to static-only)
            llm_reviewer = LLMReviewer()
            all_issues = llm_reviewer.analyze(code, language, static_issues, diff_text=diff_text)

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

            # Compute health score
            all_db_issues = ReviewIssue.query.filter_by(review_id=review_id).all()
            review.health_score = compute_health_score(all_db_issues)

            if previous_review_id and prev_review:
                old_issues = prev_review.issues.all()
                old_keys = {(i.line_number, i.message) for i in old_issues}
                new_keys = {(i.line_number, i.message) for i in all_db_issues}
                
                resolved_count = len(old_keys - new_keys)
                new_count = len(new_keys - old_keys)
                unchanged_count = len(old_keys & new_keys)
                
                review.diff_summary = f"{resolved_count} issues resolved, {new_count} new issues, {unchanged_count} unchanged"

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
                db.session.rollback()
                print(f"Could not update review {review_id} status to 'failed'.")


def process_batch(app, batch_id: str, review_ids: list[str], temp_dir: str):
    """Run analysis for multiple reviews in a batch, then aggregate.
    
    Args:
        app: Flask app instance
        batch_id: The UUID of the Batch
        review_ids: List of Review UUIDs in this batch
        temp_dir: Temporary directory to clean up after processing
    """
    with app.app_context():
        batch = db.session.get(Batch, batch_id)
        if not batch:
            print(f"Batch {batch_id} not found.")
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            return

        try:
            batch.status = "processing"
            db.session.commit()

            # Process each review synchronously in this worker thread.
            # (In production with Celery, we might fan-out, but here we process sequentially
            # to protect rate limits and keep it simple).
            for review_id in review_ids:
                process_review(app, review_id)

            # Determine overall batch status
            # If all failed, batch fails. Otherwise completes.
            all_reviews = batch.reviews.all()
            if all(r.status == 'failed' for r in all_reviews):
                batch.status = "failed"
            else:
                batch.status = "complete"
            
            batch.completed_at = datetime.now(timezone.utc)
            db.session.commit()

        except Exception as e:
            print(f"Batch {batch_id} failed: {e}")
            try:
                batch.status = "failed"
                db.session.commit()
            except Exception:
                db.session.rollback()
        finally:
            # Always clean up the temp directory to prevent disk exhaustion
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

