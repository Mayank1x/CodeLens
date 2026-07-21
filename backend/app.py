"""
Flask Application Factory — Phase 3

Sets up the Flask application with all Phase 3 components:
- SQLAlchemy database (PostgreSQL)
- JWT-based authentication
- Rate limiting (Flask-Limiter)
- ThreadPoolExecutor for async review processing
- CORS for the React frontend
- Structured error handling

Design choice: Application factory pattern (create_app function) rather than
a module-level app object. This is Flask best practice because it:
1. Allows creating multiple app instances with different configs (e.g., testing)
2. Avoids circular imports (modules import the factory, not a global app)
3. Makes the app easily testable
"""

import os
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Load environment variables from .env file (project root), override existing
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # --- Core Configuration ---
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev"),
        # 1MB max upload — covers ZIP files. Individual code snippets are
        # further validated at the route level (500KB / 5000 lines).
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,

        # SQLAlchemy database configuration
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL",
            "sqlite:///codelens_dev.db"  # Fallback for quick testing without Docker
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,  # Disable event system we don't use (saves memory)
    )

    if test_config is not None:
        # Override config for testing (e.g., use in-memory SQLite)
        app.config.from_mapping(test_config)

    # --- CORS ---
    # Restrict to the configured frontend origin. In production this is the
    # Vercel domain; in dev it defaults to localhost:5173.
    frontend_origin = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    CORS(app, resources={r"/api/*": {"origins": frontend_origin}})

    # --- Rate Limiting ---
    # 10 reviews per hour per user, as the spec requires.
    # This protects both our free LLM tier quotas AND provides fair usage.
    # We use the remote address as the key for unauthenticated endpoints,
    # but the review endpoint additionally checks per-user via the JWT.
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],  # Global defaults
        storage_uri="memory://",  # In-memory storage is fine for single-process dev
    )
    app.config["LIMITER"] = limiter

    # --- Database ---
    from database import init_db
    init_db(app)

    # --- Thread Pool Executor ---
    # Shared executor for async review processing. max_workers=4 means at most
    # 4 reviews can be processed concurrently. This is plenty for a portfolio
    # project and prevents unbounded thread creation.
    executor = ThreadPoolExecutor(max_workers=4)
    app.config["EXECUTOR"] = executor

    # --- Error Handlers ---
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File too large. Maximum size is 1MB."}), 413

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            "error": "Rate limit exceeded. Please try again later.",
            "details": "Review submissions are limited to 10 per hour per user "
                       "to ensure fair usage and keep the free LLM tier sustainable."
        }), 429

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"error": "An internal server error occurred."}), 500

    # --- Register Blueprints ---
    from api import routes
    app.register_blueprint(routes.bp)

    # Apply rate limit specifically to the review submission endpoint
    # 10 per hour is strict enough to protect the free LLM tier but generous
    # enough for real usage and demos
    limiter.limit("10 per hour")(routes.submit_review)
    limiter.limit("5 per hour")(routes.submit_batch_review)
    limiter.limit("5 per hour")(routes.submit_github_review)
    limiter.limit("5 per day")(routes.guest_login)

    # Polling endpoints must be exempted from the global "50 per hour" limit
    # because they are called every 2 seconds by the React frontend.
    limiter.exempt(routes.get_review)
    limiter.exempt(routes.get_batch)

    # --- Health Check ---
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "version": "1.0.0"})

    return app
