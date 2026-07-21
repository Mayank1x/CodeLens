"""
API Routes — Full Implementation

Defines all REST endpoints for the CodeReview AI Flask application:
  - POST /api/auth/github/callback — Exchange GitHub OAuth code for a JWT
  - POST /api/auth/github/upgrade  — Upgrade OAuth scope to 'repo'
  - POST /api/auth/guest           — Issue a temporary guest JWT
  - POST /api/review               — Submit code for async review
  - GET  /api/review/<review_id>   — Poll for review status/results
  - POST /api/review/batch         — Upload ZIP for batch review
  - POST /api/review/github        — Scan a GitHub repository
  - GET  /api/batch/<batch_id>     — Get batch status/results
  - GET  /api/github/repos         — List user's GitHub repositories
  - GET  /api/github/repos/<owner>/<repo>/tree — Get filtered file tree
  - GET  /api/history              — List past reviews (paginated)
  - GET  /api/stats                — Aggregate stats for the current user
  - GET  /api/admin/stats          — System-wide admin statistics

All endpoints except the OAuth callback and guest login require JWT authentication,
enforced by the @require_auth decorator.
"""

import os
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import func, cast, Date

from auth.middleware import require_auth
from auth.github_oauth import exchange_code_for_token, get_github_user
from auth.jwt_utils import create_token
from auth.encryption import encrypt_token, decrypt_token
from database import db
from models.user import User
from models.review import Review
from models.issue import ReviewIssue
from models.batch import Batch
from api.zip_utils import process_zip_upload
from api.github_utils import (
    list_user_repos,
    get_repo_file_tree,
    fetch_github_repo,
    parse_repo_url,
)

bp = Blueprint("api", __name__, url_prefix="/api")

# --- Input validation constants ---
# The spec says: reject code over 5,000 lines or 500KB
MAX_CODE_LINES = 5000
MAX_CODE_BYTES = 500 * 1024  # 500KB


# =============================================================================
# HELPER: Check if user is guest and block if needed
# =============================================================================

def _require_non_guest():
    """Return a JSON error response if the current user is a guest, else None."""
    if getattr(g, "is_guest", False):
        return jsonify({
            "error": "This feature requires a GitHub account. "
                     "Please sign in with GitHub to access it."
        }), 403
    return None


# =============================================================================
# AUTH ENDPOINTS
# =============================================================================

@bp.route("/auth/github/callback", methods=["POST"])
def github_auth_callback():
    """Exchange a GitHub OAuth authorization code for a JWT.

    The frontend sends the code it received from GitHub's OAuth redirect.
    We exchange it for an access token, fetch the user's profile, create
    or update the user in our database, and return a signed JWT.
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    code = data.get("code")

    if not code:
        return jsonify({"error": "Missing 'code' field in request body."}), 400

    try:
        access_token = exchange_code_for_token(code)
        github_user = get_github_user(access_token)

        user = User.query.filter_by(github_id=github_user["id"]).first()

        if user:
            user.username = github_user["login"]
            user.avatar_url = github_user["avatar_url"]
            user.github_token = encrypt_token(access_token)
        else:
            user = User(
                github_id=github_user["id"],
                username=github_user["login"],
                avatar_url=github_user["avatar_url"],
                github_token=encrypt_token(access_token),
            )
            db.session.add(user)

        db.session.commit()

        token = create_token(user.id)

        return jsonify({
            "token": token,
            "user": user.to_dict(),
            "has_repo_scope": bool(user.github_token),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/auth/github/upgrade", methods=["POST"])
@require_auth
def upgrade_github_scope():
    """Exchange the code from the 2nd OAuth flow (which requested 'repo' scope)
    and store the elevated token.
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    code = request.get_json().get("code")
    if not code:
        return jsonify({"error": "Missing 'code' field in request body."}), 400

    try:
        access_token = exchange_code_for_token(code)

        user = db.session.get(User, g.current_user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        user.github_token = encrypt_token(access_token)
        db.session.commit()

        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/auth/guest", methods=["POST"])
def guest_login():
    """Issue a temporary token for Guest Mode.

    Guest tokens include a unique guest_session_id so we can track
    which reviews belong to which guest session.
    """
    try:
        token = create_token(user_id=None, is_guest=True)
        return jsonify({
            "token": token,
            "user": {
                "id": "guest",
                "username": "Guest User",
                "avatar_url": "https://github.com/ghost.png",
            },
            "has_repo_scope": False,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    code = data.get("code", "")
    language = data.get("language", "python").lower()
    previous_review_id = data.get("previous_review_id")

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
    # For guests, we store the guest_session_id so they can retrieve their own reviews
    review = Review(
        user_id=g.current_user_id,
        guest_session_id=getattr(g, "guest_session_id", None),
        language=language,
        code_snippet=code,
        status="pending",
    )
    db.session.add(review)
    db.session.commit()

    # --- Dispatch to background worker ---
    from api.review_worker import process_review
    executor = current_app.config["EXECUTOR"]
    executor.submit(process_review, current_app._get_current_object(), review.id, previous_review_id)

    return jsonify({
        "review_id": review.id,
        "status": "pending",
    }), 202


@bp.route("/review/<review_id>", methods=["GET"])
@require_auth
def get_review(review_id):
    """Poll for a review's status and results.

    Security: Users can only access their own reviews.
    Guests can only access reviews from their own session.
    """
    review = db.session.get(Review, review_id)

    if not review:
        return jsonify({"error": "Review not found."}), 404

    # Security check: authenticated users can only see their own reviews
    if g.is_guest:
        # Guest: check guest_session_id instead of user_id
        if review.guest_session_id != getattr(g, "guest_session_id", None):
            return jsonify({"error": "Review not found."}), 404
    else:
        if review.user_id != g.current_user_id:
            return jsonify({"error": "Review not found."}), 404

    include_issues = review.status == "complete"
    return jsonify(review.to_dict(include_issues=include_issues))


# =============================================================================
# BATCH & GITHUB ENDPOINTS
# =============================================================================

@bp.route("/review/batch", methods=["POST"])
@require_auth
def submit_batch_review():
    """Upload a ZIP file for batch code review.

    Guests cannot use this endpoint — it requires a GitHub account
    for review history tracking.
    """
    guest_block = _require_non_guest()
    if guest_block:
        return guest_block

    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not file.filename.endswith(".zip"):
        return jsonify({"error": "Only .zip files are supported"}), 400

    temp_dir, files_to_analyze, skipped_count, error = process_zip_upload(file.stream)

    if error:
        return jsonify({"error": error}), 400

    batch = Batch(
        user_id=g.current_user_id,
        source="zip",
        status="pending",
        total_files=len(files_to_analyze),
        skipped_files=skipped_count,
    )
    db.session.add(batch)
    db.session.flush()

    reviews = []
    for file_data in files_to_analyze:
        with open(file_data["absolute_path"], "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        review = Review(
            user_id=g.current_user_id,
            language=file_data["language"],
            code_snippet=code,
            filename=file_data["relative_path"],
            status="pending",
            batch_id=batch.id,
        )
        db.session.add(review)
        reviews.append(review)

    db.session.commit()

    from api.review_worker import process_batch
    executor = current_app.config["EXECUTOR"]
    executor.submit(
        process_batch,
        current_app._get_current_object(),
        batch.id,
        [r.id for r in reviews],
        temp_dir,
    )

    return jsonify({
        "batch_id": batch.id,
        "status": "pending",
        "total_files": batch.total_files,
    }), 202


@bp.route("/review/github", methods=["POST"])
@require_auth
def submit_github_review():
    """Scan a GitHub repository.

    Requires GitHub OAuth with repo scope. Accepts an optional list of
    selected_files — if provided, only those files are scanned. Otherwise
    the first 30 supported files are scanned automatically.
    """
    guest_block = _require_non_guest()
    if guest_block:
        return guest_block

    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    repo_url = data.get("repo_url")
    selected_files = data.get("selected_files")  # Optional list of file paths

    if not repo_url:
        return jsonify({"error": "Missing 'repo_url'."}), 400

    user = db.session.get(User, g.current_user_id)
    if not user or not user.github_token:
        return jsonify({
            "error": "GitHub connection required. "
                     "Please connect your repository access first."
        }), 403

    # Fetch and filter files (optionally only selected ones)
    temp_dir, files_to_analyze, skipped_count, error = fetch_github_repo(
        repo_url, decrypt_token(user.github_token), selected_files
    )

    if error:
        return jsonify({"error": error}), 400

    batch = Batch(
        user_id=g.current_user_id,
        source="github",
        source_url=repo_url,
        status="pending",
        total_files=len(files_to_analyze),
        skipped_files=skipped_count,
    )
    db.session.add(batch)
    db.session.flush()

    reviews = []
    for file_data in files_to_analyze:
        with open(file_data["absolute_path"], "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        review = Review(
            user_id=g.current_user_id,
            language=file_data["language"],
            code_snippet=code,
            filename=file_data["relative_path"],
            status="pending",
            batch_id=batch.id,
        )
        db.session.add(review)
        reviews.append(review)

    db.session.commit()

    from api.review_worker import process_batch
    executor = current_app.config["EXECUTOR"]
    executor.submit(
        process_batch,
        current_app._get_current_object(),
        batch.id,
        [r.id for r in reviews],
        temp_dir,
    )

    return jsonify({
        "batch_id": batch.id,
        "status": "pending",
        "total_files": batch.total_files,
    }), 202


@bp.route("/batch/<batch_id>", methods=["GET"])
@require_auth
def get_batch(batch_id):
    """Get the aggregated status and results of a batch."""
    batch = db.session.get(Batch, batch_id)

    if not batch:
        return jsonify({"error": "Batch not found."}), 404

    if batch.user_id != g.current_user_id:
        return jsonify({"error": "Batch not found."}), 404

    return jsonify(batch.to_dict(include_reviews=True))


# =============================================================================
# GITHUB REPO BROWSING ENDPOINTS
# =============================================================================

@bp.route("/github/repos", methods=["GET"])
@require_auth
def get_github_repos():
    """List the authenticated user's GitHub repositories.

    Query parameters:
        page (int): Page number, default 1.
        per_page (int): Results per page, default 20, max 100.
        search (str): Filter repos by name.

    Requires a GitHub token — not available to guests.
    """
    guest_block = _require_non_guest()
    if guest_block:
        return guest_block

    user = db.session.get(User, g.current_user_id)
    if not user or not user.github_token:
        return jsonify({
            "error": "GitHub connection required. "
                     "Please connect your repository access first."
        }), 403

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)

    repos, has_next, error = list_user_repos(
        decrypt_token(user.github_token), page, per_page, search
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "repos": repos,
        "page": page,
        "has_next": has_next,
    })


@bp.route("/github/repos/<owner>/<repo>/tree", methods=["GET"])
@require_auth
def get_github_repo_tree(owner, repo):
    """Get the filtered file tree of a GitHub repository.

    Returns all supported source files with their paths, languages,
    and sizes. The frontend uses this to show a file picker for repos
    that have more than 30 supported files.
    """
    guest_block = _require_non_guest()
    if guest_block:
        return guest_block

    user = db.session.get(User, g.current_user_id)
    if not user or not user.github_token:
        return jsonify({"error": "GitHub connection required."}), 403

    repo_path = f"{owner}/{repo}"
    files, total_files, skipped_count, error = get_repo_file_tree(
        repo_path, decrypt_token(user.github_token)
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({
        "files": files,
        "total_files": total_files,
        "supported_files": len(files),
        "skipped_files": skipped_count,
    })


# =============================================================================
# HISTORY & STATS ENDPOINTS
# =============================================================================

@bp.route("/history", methods=["GET"])
@require_auth
def get_history():
    """List past reviews for the authenticated user, paginated."""
    if getattr(g, "is_guest", False):
        return jsonify({
            "reviews": [], "page": 1, "per_page": 10, "total": 0, "pages": 0
        })

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    per_page = min(max(per_page, 1), 50)

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
    """Return aggregate statistics for the authenticated user."""
    if getattr(g, "is_guest", False):
        return jsonify({
            "total_reviews": 0,
            "average_issues_per_review": 0,
            "category_breakdown": {},
            "severity_breakdown": {},
        })

    user_id = g.current_user_id

    total_reviews = Review.query.filter_by(user_id=user_id).count()

    if total_reviews == 0:
        return jsonify({
            "total_reviews": 0,
            "average_issues_per_review": 0,
            "category_breakdown": {},
            "severity_breakdown": {},
        })

    total_issues = (
        db.session.query(func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .filter(Review.user_id == user_id)
        .scalar()
    ) or 0

    avg_issues = round(total_issues / total_reviews, 2) if total_reviews > 0 else 0

    category_rows = (
        db.session.query(ReviewIssue.category, func.count(ReviewIssue.id))
        .join(Review, ReviewIssue.review_id == Review.id)
        .filter(Review.user_id == user_id)
        .group_by(ReviewIssue.category)
        .all()
    )
    category_breakdown = {row[0]: row[1] for row in category_rows}

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


# =============================================================================
# ADMIN ENDPOINT
# =============================================================================

@bp.route("/admin/stats", methods=["GET"])
@require_auth
def get_admin_stats():
    """Return system-wide statistics for the admin dashboard.

    Protected by checking the username against the ADMIN_USERS env variable.
    Returns: total users, total reviews, reviews by day, issue categories,
    LLM provider health, guest vs authenticated split, reviews by language.
    """
    if getattr(g, "is_guest", False):
        return jsonify({"error": "Guests cannot view admin statistics."}), 403

    admin_users = os.environ.get("ADMIN_USERS", "").split(",")
    user = db.session.get(User, g.current_user_id)
    if not user or user.username not in admin_users:
        return jsonify({"error": "Forbidden. User is not an admin."}), 403

    # --- Basic counts ---
    total_users = User.query.count()
    total_reviews = Review.query.count()

    # --- Reviews by language ---
    language_rows = (
        db.session.query(Review.language, func.count(Review.id))
        .group_by(Review.language)
        .all()
    )
    reviews_by_language = {row[0]: row[1] for row in language_rows}

    # --- Global average health score ---
    avg_score = (
        db.session.query(func.avg(Review.health_score))
        .filter(Review.health_score.isnot(None))
        .scalar()
    )

    # --- Reviews by day (last 30 days) ---
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily_rows = (
        db.session.query(
            cast(Review.created_at, Date).label("day"),
            func.count(Review.id),
        )
        .filter(Review.created_at >= thirty_days_ago)
        .group_by(cast(Review.created_at, Date))
        .order_by(cast(Review.created_at, Date))
        .all()
    )
    reviews_by_day = [
        {"date": row[0].isoformat() if row[0] else None, "count": row[1]}
        for row in daily_rows
    ]

    # --- Most common issue categories (global) ---
    category_rows = (
        db.session.query(ReviewIssue.category, func.count(ReviewIssue.id))
        .group_by(ReviewIssue.category)
        .order_by(func.count(ReviewIssue.id).desc())
        .all()
    )
    top_categories = {row[0]: row[1] for row in category_rows}

    # --- Guest vs authenticated split ---
    guest_reviews = Review.query.filter(Review.user_id.is_(None)).count()
    auth_reviews = total_reviews - guest_reviews

    # --- LLM provider health (from in-memory counters) ---
    from api.review_worker import llm_health_stats
    llm_health = dict(llm_health_stats)

    return jsonify({
        "total_users": total_users,
        "total_reviews": total_reviews,
        "reviews_by_language": reviews_by_language,
        "average_health_score": round(avg_score, 1) if avg_score else 0,
        "reviews_by_day": reviews_by_day,
        "top_categories": top_categories,
        "guest_reviews": guest_reviews,
        "auth_reviews": auth_reviews,
        "llm_health": llm_health,
    })
