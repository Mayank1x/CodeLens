"""
API Routes

Defines the REST endpoints for the Flask application.
The primary endpoint is POST /api/v1/analyze which accepts source code
and returns the static + LLM analysis results.
"""

from flask import Blueprint, request, jsonify
from static_analyzer.analyzer import StaticAnalyzer, EXTENSION_TO_LANGUAGE
from llm_reviewer.reviewer import LLMReviewer

bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Max code length to analyze (approx 5000 lines) to prevent LLM abuse
MAX_CODE_LENGTH = 150000

@bp.route("/analyze", methods=["POST"])
def analyze_code():
    """
    Analyzes provided source code and returns the found issues.
    
    Expected JSON payload:
    {
        "code": "print('hello')",
        "language": "python" (optional, will be auto-detected if omitted or mapped to unknown)
    }
    
    Returns:
    {
        "status": "success",
        "analysis_time_ms": 124.5,
        "total_issues": 3,
        "issues": [ ... ]
    }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    code = data.get("code", "")
    
    if not code:
        return jsonify({"error": "No code provided for analysis."}), 400
        
    if len(code) > MAX_CODE_LENGTH:
        return jsonify({
            "error": f"Code exceeds maximum allowed length ({MAX_CODE_LENGTH} characters)."
        }), 400

    # Determine language
    language = data.get("language")
    if not language:
        # Fallback to python if they don't provide one, or we could require it.
        # Since the frontend will have a file extension, it should usually provide it.
        language = "python"
    
    # Normalize language string
    language = language.lower()
    
    import time
    start_time = time.perf_counter()

    try:
        # 1. Run Static Analysis
        static_analyzer = StaticAnalyzer()
        issues, static_ms = static_analyzer.analyze_timed(code, language)
        
        # 2. Run LLM Analysis (if keys are configured)
        # The reviewer gracefully falls back to just static issues if it fails
        llm_reviewer = LLMReviewer()
        final_issues = llm_reviewer.analyze(code, language, issues)
        
        total_ms = (time.perf_counter() - start_time) * 1000

        return jsonify({
            "status": "success",
            "language": language,
            "analysis_time_ms": round(total_ms, 2),
            "total_issues": len(final_issues),
            "issues": [issue.to_dict() for issue in final_issues]
        })

    except Exception as e:
        # Log the actual error to server console for debugging
        print(f"Analysis failed: {e}")
        return jsonify({
            "error": "An error occurred during code analysis.",
            "details": str(e)
        }), 500
