"""Output truncation guardrail plugin package."""

from mth_plugins.guards.truncation.plugin import apply
from mth_plugins.guards.truncation.truncation import (
    TruncationResult,
    format_size,
    truncate_head,
    truncate_tail,
)

__all__ = [
    "TruncationResult",
    "apply",
    "format_size",
    "truncate_head",
    "truncate_tail",
]
