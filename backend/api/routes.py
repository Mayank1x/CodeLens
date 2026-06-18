"""
API Routes — Phase 3 Full Implementation

Defines all REST endpoints for the CodeReview AI Flask application:
  - POST /api/auth/github/callback — Exchange GitHub OAuth code for a JWT
  - POST /api/review                — Submit code for async review
  - GET  /api/review/<review_id>    — Poll for review status/results
  - GET  /api/history               — List past reviews (paginated)
  - GET  /api/stats                 — Aggregate stats for the current user

All endpoints except the OAuth callback require JWT authentication,
enforced by the @require_auth decorator.
"""

from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import func

from auth.middleware import require_auth
from auth.github_oauth import exchange_code_for_token, get_github_user
from auth.jwt_utils import create_token
from database import db
from models.user import User
from models.review import Review
from models.issue import ReviewIssue

bp = Blueprint("api", __name__, url_prefix="/api")

# --- Input validation constants ---
# The spec says: reject code over 5,000 lines or 500KB
MAX_CODE_LINES = 5000
MAX_CODE_BYTES = 500 * 1024  # 500KB


# =============================================================================
# AUTH ENDPOINT
# =============================================================================

@bp.route("/auth/github/callback", methods=["POST"])
def github_auth_callback():
    """Exchange a GitHub OAuth authorization code for a JWT.

    The frontend sends the code it received from GitHub's OAuth redirect.
    We exchange it for an access token, fetch the user's profile, create
    or update the user in our database, and return a signed JWT.

    Expected JSON payload:
        { "code": "abc123..." }

    Returns:
        { "token": "<jwt>", "user": { ... } }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    code = data.get("code")

    if not code:
        return jsonify({"error": "Missing 'code' field in request body."}), 400

    try:
        # Step 1: Exchange the temporary code for a GitHub access token
        access_token = exchange_code_for_token(code)

        # Step 2: Fetch the user's GitHub profile
        github_user = get_github_user(access_token)

        # Step 3: Find or create the user in our database
        user = User.query.filter_by(github_id=github_user["id"]).first()

        if user:
            # Update profile info in case they changed their username/avatar
            user.username = github_user["login"]
            user.avatar_url = github_user["avatar_url"]
        else:
            user = User(
                github_id=github_user["id"],
                username=github_user["login"],
                avatar_url=github_user["avatar_url"],
            )
            db.session.add(user)

        db.session.commit()

        # Step 4: Create a JWT for our API
        token = create_token(user.id)

        return jsonify({
            "token": token,
            "user": user.to_dict(),
        })

    except ValueError as e:
        # exchange_code_for_token or get_github_user raised a clear error
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"GitHub OAuth error: {e}")
        return jsonify({"error": "Authentication failed. Please try again."}), 500


# =============================================================================
# REVIEW ENDPOINTS
# =============================================================================

@bp.route("/review", methods=["POST"])
@require_auth
def submit_review():
    """Submit code for async analysis.

    Creates a Review record with status 'pending' and dispatches a background
    worker to run the actual analysis. Returns the review_id immediately so
    the client can poll for results.

    Expected JSON payload:
        {
            "code": "def foo(): ...",
            "language": "python"  (optional, defaults to "python")
        }

    Returns:
        { "review_id": "<uuid>", "status": "pending" }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    code = data.get("code", "")
    language = data.get("language", "python").lower()

    # --- Input validation ---
    if not code or not code.strip():
        return jsonify({"error": "No code provided for analysis."}), 400

    code_bytes = len(code.encode("utf-8"))
    if code_bytes > MAX_CODE_BYTES:
        return jsonify({
            "error": f"Code exceeds maximum allowed size ({MAX_CODE_BYTES // 1024}KB). "
                     f"Your submission is {code_bytes // 1024}KB."
        }), 400

    line_count = code.count("\n") + 1
    if line_count > MAX_CODE_LINES:
        return jsonify({
            "error": f"Code exceeds maximum allowed line count ({MAX_CODE_LINES} lines). "
                     f"Your submission has {line_count} lines."
        }), 400

    # --- Create the review record ---
    review = Review(
        user_id=g.current_user_id,
        language=language,
        code_snippet=code,
        status="pending",
    )
    db.session.add(review)
    db.session.commit()

    # --- Dispatch to background worker ---
    # We use the ThreadPoolExecutor attached to the app (created in app.py)
    # rather than creating a new one per request. This gives us a bounded
    # pool of worker threads and prevents unbounded thread creation.
    from api.review_worker import process_review
    executor = current_app.config["EXECUTOR"]
    executor.submit(process_review, current_app._get_current_object(), review.id)

    return jsonify({
        "review_id": review.id,
        "status": "pending",
    }), 202  # 202 Accepted — the request has been accepted for processing


@bp.route("/review/<review_id>", methods=["GET"])
@require_auth
def get_review(review_id):
    """Poll for a review's status and results.

    Returns the review with its full list of issues if the status is 'complete'.
    For other statuses, issues are omitted (there aren't any yet).

    Security: Users can only access their own reviews.

    Returns:
        { "id": "...", "status": "complete", "issues": [...], ... }
    """
    review = db.session.get(Review, review_id)

    if not review:
        return jsonify({"error": "Review not found."}), 404

    # Security check: prevent users from accessing other users' reviews
    if review.user_id != g.current_user_id:
        return jsonify({"error": "Review not found."}), 404

    # Include full issue list only when the review is complete
    include_issues = review.status == "complete"

    return jsonify(review.to_dict(include_issues=include_issues))


# =============================================================================
# HISTORY & STATS ENDPOINTS
# =============================================================================

@bp.route("/history", methods=["GET"])
@require_auth
def get_history():
    """List past reviews for the authenticated user, paginated.

    Query parameters:
        page (int): Page number, 1-indexed. Default: 1
        per_page (int): Items per page, max 50. Default: 10

    Returns:
        {
            "reviews": [...],
            "page": 1,
            "per_page": 10,
            "total": 42,
            "pages": 5
        }
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    # Clamp per_page to prevent abusive queries
    per_page = min(max(per_page, 1), 50)

    # Query reviews for this user, newest first
    pagination = (
        Review.query
        .filter_by(user_id=g.current_user_id)
        .order_by(Review.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "reviews": [review.to_dict(include_issues=False) for review in pagination.items],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@bp.route("/stats", methods=["GET"])
@require_auth
def get_stats():
    """Return aggregate statistics for the authenticated user.

    Returns:
        {
            "total_reviews": 42,
            "average_issues_per_review": 3.5,
            "category_breakdown": { "security": 12, "bug": 8, ... },
            "severity_breakdown": { "critical": 5, "warning": 10, ... }
        }
    """
    user_id = g.current_user_id

    # Total reviews
    total_reviews = Review.query.filter_by(user_id=user_id).count()

    if total_reviews == 0:
        return jsonify({
            "total_reviews": 0,
            "average_issues_per_review": 0,
            "category_breakdown": {},
            "severity_breakdown": {},
        })

    # Total issues across all of this user's reviews
    total_issues = (
        db.session.query(func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .filter(Review.user_id == user_id)
        .scalar()
    ) or 0

    avg_issues = round(total_issues / total_reviews, 2) if total_reviews > 0 else 0

    # Category breakdown (e.g., {"security": 12, "bug": 8})
    category_rows = (
        db.session.query(ReviewIssue.category, func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .filter(Review.user_id == user_id)
        .group_by(ReviewIssue.category)
        .all()
    )
    category_breakdown = {row[0]: row[1] for row in category_rows}

    # Severity breakdown (e.g., {"critical": 5, "warning": 10})
    severity_rows = (
        db.session.query(ReviewIssue.severity, func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .filter(Review.user_id == user_id)
        .group_by(ReviewIssue.severity)
        .all()
    )
    severity_breakdown = {row[0]: row[1] for row in severity_rows}

    return jsonify({
        "total_reviews": total_reviews,
        "average_issues_per_review": avg_issues,
        "category_breakdown": category_breakdown,
        "severity_breakdown": severity_breakdown,
    })
