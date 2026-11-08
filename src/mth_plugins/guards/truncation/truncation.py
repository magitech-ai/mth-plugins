"""Output truncation middleware and guardrails.

Prevents unbounded tool output from overflowing model context windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 51_200


@dataclass(frozen=True)
class TruncationResult:
    """Bounded view of tool output with metadata."""

    text: str
    truncated: bool
    strategy: Literal["head", "tail"] | None
    total_lines: int
    shown_start: int | None
    shown_end: int | None
    total_bytes: int


def format_size(num_bytes: int) -> str:
    """Formats byte counts into human-readable strings (B, KB, MB)."""
    if num_bytes < 1024:
        return f"{num_bytes}B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f}KB"
    return f"{num_bytes / (1024 * 1024):.1f}MB"


def _split_lines(content: str) -> list[str]:
    if not content:
        return []
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return lines


def _line_bytes(line: str) -> int:
    return len(line.encode("utf-8"))


def truncate_head(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    """Keeps the initial lines within line and byte limits."""
    total_bytes = len(content.encode("utf-8"))
    lines = _split_lines(content)
    total_lines = len(lines)

    kept: list[str] = []
    used = 0
    truncated = False
    for line in lines:
        if len(kept) >= max_lines:
            truncated = True
            break
        cost = _line_bytes(line) + (1 if kept else 0)
        if used + cost > max_bytes:
            truncated = True
            break
        kept.append(line)
        used += cost

    if not truncated:
        return TruncationResult(
            text=content,
            truncated=False,
            strategy=None,
            total_lines=total_lines,
            shown_start=None,
            shown_end=None,
            total_bytes=total_bytes,
        )

    return TruncationResult(
        text="\n".join(kept),
        truncated=True,
        strategy="head",
        total_lines=total_lines,
        shown_start=1 if kept else None,
        shown_end=len(kept) if kept else None,
        total_bytes=total_bytes,
    )


def _tail_suffix(line: str, max_bytes: int) -> str:
    chars = list(line)
    used = 0
    keep = 0
    for char in reversed(chars):
        cost = len(char.encode("utf-8"))
        if used + cost > max_bytes:
            break
        used += cost
        keep += 1
    return "".join(chars[len(chars) - keep :]) if keep else ""


def truncate_tail(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TruncationResult:
    """Keeps the final lines within line and byte limits."""
    total_bytes = len(content.encode("utf-8"))
    lines = _split_lines(content)
    total_lines = len(lines)

    kept: list[str] = []
    used = 0
    truncated = False
    for line in reversed(lines):
        if len(kept) >= max_lines:
            truncated = True
            break
        cost = _line_bytes(line) + (1 if kept else 0)
        if used + cost > max_bytes:
            truncated = True
            if not kept:
                suffix = _tail_suffix(line, max_bytes)
                if suffix:
                    kept.append(suffix)
            break
        kept.append(line)
        used += cost

    if not truncated:
        return TruncationResult(
            text=content,
            truncated=False,
            strategy=None,
            total_lines=total_lines,
            shown_start=None,
            shown_end=None,
            total_bytes=total_bytes,
        )

    kept.reverse()
    shown_end = total_lines
    shown_start = total_lines - len(kept) + 1 if kept else None

    return TruncationResult(
        text="\n".join(kept),
        truncated=True,
        strategy="tail",
        total_lines=total_lines,
        shown_start=shown_start,
        shown_end=shown_end if kept else None,
        total_bytes=total_bytes,
    )
