"""Filesystem tool handler for reading files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

_BINARY_PROBE_BYTES = 8192


def _split_file_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return lines


async def handle_read_file(args: dict[str, Any]) -> str:
    """Reads a file with optional 1-indexed line offset and limit pagination."""
    path_str = args.get("path")
    if not path_str:
        return "Error: 'path' argument is required."

    offset = args.get("offset")
    limit = args.get("limit")

    if offset is not None and offset < 1:
        return f"Error: Invalid offset '{offset}'. Must be 1 or greater."
    if limit is not None and limit < 1:
        return f"Error: Invalid limit '{limit}'. Must be 1 or greater."

    file_path = Path(path_str)
    if not file_path.exists():
        return f"Error: File not found: {path_str}"

    if file_path.is_dir():
        skill_md = file_path / "SKILL.md"
        if skill_md.is_file():
            file_path = skill_md
        else:
            return f"Error: Cannot read directory '{path_str}'"

    def _read_bytes() -> bytes:
        with file_path.open("rb") as handle:
            return handle.read()

    raw = await asyncio.to_thread(_read_bytes)
    if b"\x00" in raw[:_BINARY_PROBE_BYTES]:
        return f"Error: Binary file not supported: {path_str}"

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"Error: Binary file not supported: {path_str}"

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = _split_file_lines(text)
    total = len(lines)

    start = (offset or 1) - 1
    if start >= total > 0:
        return f"Error: Offset {offset} is beyond end of file ({total} lines total)"

    window = lines[start:]
    if limit is not None and len(window) > limit:
        window = window[:limit]

    return "\n".join(window)
