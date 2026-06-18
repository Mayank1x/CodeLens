"""
Flask Application Factory

This module sets up the Flask application, configures CORS, loads
environment variables, and registers the API blueprints.
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    
    # Configure CORS to allow the React frontend to communicate with the API
    # In production, origins should be restricted to the specific frontend domain
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev"),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024, # 1MB max upload size for source code files
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Global error handler for file size limits
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File too large. Maximum size is 1MB."}), 413

    # Global error handler for unhandled exceptions
    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"error": "An internal server error occurred."}), 500

    # Register blueprints (routes)
    from api import routes
    app.register_blueprint(routes.bp)
    
    # Health check endpoint
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "version": "1.0.0"})

    return app
