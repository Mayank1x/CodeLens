"""
Data models for the static analysis engine.

Using a dataclass instead of a plain dict for type safety and self-documentation.
The Issue schema is shared with the LLM reviewer (Phase 2) so both layers
produce consistent output that can be merged and deduplicated.
"""

from dataclasses import dataclass, asdict
from typing import Literal


# Using Literal types to enforce the allowed values at the type-checking level.
# This also serves as living documentation of the valid enum values.
Severity = Literal["critical", "warning", "info"]
Category = Literal["bug", "security", "style", "performance"]


@dataclass
class Issue:
    """Represents a single code issue found by analysis.

    Attributes:
        line_number: The 1-indexed line where the issue was found.
        severity: How urgent the issue is — 'critical', 'warning', or 'info'.
        category: The kind of issue — 'bug', 'security', 'style', or 'performance'.
        message: A human-readable description of what's wrong.
        suggestion: A concrete recommendation for how to fix it.
    """

    line_number: int
    severity: Severity
    category: Category
    message: str
    suggestion: str

    def to_dict(self) -> dict:
        """Convert to a plain dictionary for JSON serialization.

        We use dataclasses.asdict() rather than hand-rolling this because
        it handles nested dataclasses automatically if we ever add them.
        """
        return asdict(self)
