"""
Prompt Construction Module

This module isolates the LLM prompt engineering. Keeping the prompt logic
separate from the execution logic makes it easier to test and iterate on the
instructions.
"""

from static_analyzer.models import Issue


def build_review_prompt(code: str, language: str, static_issues: list[Issue]) -> str:
    """Constructs the prompt instructing the LLM on how to review the code.

    Design decision: We explicitly list the issues already found by the
    static analyzer and instruct the LLM NOT to flag them again. This is
    crucial for a two-layer system to prevent duplicate noise.
    """
    prompt = f"""
You are an expert senior software engineer performing a code review.
Please analyze the following {language} code for semantic bugs, race conditions,
resource leaks, architectural flaws, and bad practices.

DO NOT flag syntax errors. Assume the code compiles/runs.
DO NOT focus on trivial style issues (like line length) unless they severely impact readability.

CODE TO REVIEW:
```
{code}
```

IMPORTANT: A static analysis tool has already run on this code and found the following issues.
DO NOT report these issues again. Focus ONLY on things the static analyzer missed:

STATIC ANALYSIS FINDINGS:
"""

    if not static_issues:
        prompt += "No static issues found.\n"
    else:
        for issue in static_issues:
            prompt += f"- Line {issue.line_number}: [{issue.category}] {issue.message}\n"

    prompt += """
You MUST output your response as a strict JSON object containing a single key "issues"
which is an array of objects. Do not include any markdown formatting (like ```json).
Your response must exactly match this JSON schema:

{
  "issues": [
    {
      "line_number": <integer, the 1-indexed line number where the issue occurs. Use 1 if it applies to the whole file>,
      "severity": <string, exactly one of: "critical", "warning", "info">,
      "category": <string, exactly one of: "bug", "security", "style", "performance">,
      "message": <string, a concise explanation of what is wrong>,
      "suggestion": <string, a concrete recommendation for how to fix it>
    }
  ]
}

If you find zero issues, return {"issues": []}.
Output ONLY valid JSON.
"""
    return prompt
