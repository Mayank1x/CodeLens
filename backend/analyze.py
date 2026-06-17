#!/usr/bin/env python3
"""
CodeReview AI — CLI Entry Point for Static Analysis

Usage:
    python analyze.py <file_path>          # Analyze a file (language auto-detected)
    python analyze.py <file_path> --lang python  # Specify language explicitly
    python analyze.py <file_path> --json   # Output as JSON instead of formatted text

This CLI is the Phase 1 deliverable — a standalone tool that can analyze
source code files and print all issues found by the static analysis engine.
In Phase 2, this will be extended with an --llm flag for LLM-based analysis.

Examples:
    python analyze.py sample.py
    python analyze.py script.js --lang javascript
    python analyze.py buggy_code.py --json
"""

import argparse
import json
import os
import sys
import time

# Force UTF-8 output on Windows to handle Unicode box-drawing chars and emoji.
# Without this, Python 3.9 on Windows defaults to cp1252 which can't encode them.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        # Python < 3.7 fallback — shouldn't happen but be safe
        pass

# Add the parent directory to the path so we can import static_analyzer
# when running this script directly (not as a package).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from static_analyzer.analyzer import StaticAnalyzer, EXTENSION_TO_LANGUAGE
from static_analyzer.models import Issue


# ANSI color codes for terminal output.
# Using a simple dict instead of a library like colorama to keep
# dependencies minimal — this is a developer tool, not a user-facing app.
COLORS = {
    "critical": "\033[91m",  # Red
    "warning": "\033[93m",   # Yellow
    "info": "\033[96m",      # Cyan
    "reset": "\033[0m",      # Reset
    "bold": "\033[1m",       # Bold
    "dim": "\033[2m",        # Dim
}

# Severity icons for visual scanning in terminal output
SEVERITY_ICONS = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}

# Category labels for display
CATEGORY_LABELS = {
    "bug": "Bug",
    "security": "Security",
    "style": "Style",
    "performance": "Performance",
}


def main():
    """Parse arguments and run static analysis on the specified file."""
    parser = argparse.ArgumentParser(
        description="CodeReview AI — Static Code Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze.py sample.py                  Analyze a Python file
  python analyze.py script.js --lang javascript Analyze with explicit language
  python analyze.py code.py --json              Output as JSON
        """,
    )
    parser.add_argument(
        "file",
        help="Path to the source code file to analyze.",
    )
    parser.add_argument(
        "--lang",
        choices=["python", "javascript", "java", "cpp"],
        default=None,
        help="Programming language (auto-detected from extension if not specified).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON instead of formatted text.",
    )

    args = parser.parse_args()

    # Read the file
    if not os.path.isfile(args.file):
        print(f"Error: File '{args.file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            code = f.read()
    except UnicodeDecodeError:
        print(f"Error: File '{args.file}' is not a valid text file.", file=sys.stderr)
        sys.exit(1)

    # Detect language from file extension if not specified
    language = args.lang
    if language is None:
        ext = os.path.splitext(args.file)[1].lower()
        language = EXTENSION_TO_LANGUAGE.get(ext)
        if language is None:
            print(
                f"Error: Cannot detect language from extension '{ext}'. "
                f"Use --lang to specify the language explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Run analysis
    analyzer = StaticAnalyzer()
    issues, elapsed_ms = analyzer.analyze_timed(code, language)

    # Output results
    if args.output_json:
        _output_json(issues, elapsed_ms, args.file, language)
    else:
        _output_formatted(issues, elapsed_ms, args.file, language, code)


def _output_json(issues: list[Issue], elapsed_ms: float, filepath: str, language: str):
    """Output analysis results as a JSON document."""
    result = {
        "file": filepath,
        "language": language,
        "analysis_time_ms": round(elapsed_ms, 2),
        "total_issues": len(issues),
        "issues": [issue.to_dict() for issue in issues],
        "summary": {
            "critical": sum(1 for i in issues if i.severity == "critical"),
            "warning": sum(1 for i in issues if i.severity == "warning"),
            "info": sum(1 for i in issues if i.severity == "info"),
        },
    }
    print(json.dumps(result, indent=2))


def _output_formatted(
    issues: list[Issue], elapsed_ms: float, filepath: str, language: str, code: str
):
    """Output analysis results as formatted, human-readable text with colors."""
    lines = code.split("\n")

    # Header
    print()
    print(f"{COLORS['bold']}╔══════════════════════════════════════════════════╗{COLORS['reset']}")
    print(f"{COLORS['bold']}║          CodeReview AI — Static Analysis         ║{COLORS['reset']}")
    print(f"{COLORS['bold']}╚══════════════════════════════════════════════════╝{COLORS['reset']}")
    print()
    print(f"  File:     {filepath}")
    print(f"  Language: {language}")
    print(f"  Analysis: {elapsed_ms:.1f}ms")
    print()

    if not issues:
        print(f"  {COLORS['bold']}✅ No issues found! Your code looks clean.{COLORS['reset']}")
        print()
        return

    # Summary counts
    critical = sum(1 for i in issues if i.severity == "critical")
    warning = sum(1 for i in issues if i.severity == "warning")
    info = sum(1 for i in issues if i.severity == "info")

    print(f"  Found {len(issues)} issue(s): ", end="")
    parts = []
    if critical:
        parts.append(f"{COLORS['critical']}{critical} critical{COLORS['reset']}")
    if warning:
        parts.append(f"{COLORS['warning']}{warning} warning{COLORS['reset']}")
    if info:
        parts.append(f"{COLORS['info']}{info} info{COLORS['reset']}")
    print(", ".join(parts))
    print()

    # Print each issue with context
    print(f"{'─' * 60}")
    for i, issue in enumerate(issues, start=1):
        color = COLORS.get(issue.severity, "")
        icon = SEVERITY_ICONS.get(issue.severity, "")
        category = CATEGORY_LABELS.get(issue.category, issue.category)

        print(
            f"\n  {icon} {color}[{issue.severity.upper()}]{COLORS['reset']} "
            f"{COLORS['dim']}[{category}]{COLORS['reset']} "
            f"Line {issue.line_number}"
        )
        print(f"  {issue.message}")

        # Show the offending line of code for context
        if 1 <= issue.line_number <= len(lines):
            line_content = lines[issue.line_number - 1]
            print(f"  {COLORS['dim']}  {issue.line_number} │ {line_content.rstrip()}{COLORS['reset']}")

        print(f"  {COLORS['bold']}💡 {issue.suggestion}{COLORS['reset']}")

        if i < len(issues):
            print(f"  {'─' * 56}")

    print(f"\n{'─' * 60}")
    print()


if __name__ == "__main__":
    main()
