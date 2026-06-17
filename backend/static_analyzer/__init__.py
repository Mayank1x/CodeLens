# static_analyzer — Custom rule-based code analysis engine.
# No external APIs or network calls. Designed to run in < 50ms for 200-line files.
# Each rule is a standalone module in the rules/ package, making it easy to
# add, remove, or test rules independently.

from .analyzer import StaticAnalyzer
from .models import Issue

__all__ = ["StaticAnalyzer", "Issue"]
