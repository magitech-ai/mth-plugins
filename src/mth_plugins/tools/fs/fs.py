"""Filesystem tool handlers for reading, writing, and editing files."""

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


async def handle_write_file(args: dict[str, Any]) -> str:
    """Writes content to a file at the given path, creating parent directories."""
    path_str = args.get("path")
    if not path_str:
        return "Error: 'path' argument is required."
    content = args.get("content", "")

    file_path = Path(path_str)

    def _write() -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_write)
    return f"Successfully wrote to {path_str}"


async def handle_edit_file(args: dict[str, Any]) -> str:
    """Replaces target string with replacement string in the specified file."""
    path_str = args.get("path")
    target = args.get("target")
    replacement = args.get("replacement", "")

    if not path_str or target is None:
        return "Error: 'path' and 'target' arguments are required."

    file_path = Path(path_str)
    if not file_path.exists():
        return f"Error: File not found: {path_str}"

    def _perform_edit() -> str:
        content = file_path.read_text(encoding="utf-8")
        count = content.count(target)
        if count == 0:
            return f"Error: Target string not found in {path_str}"
        if count > 1:
            return (
                f"Error: Target string matched {count} times in {path_str}. "
                "Must match uniquely (exactly 1 occurrence)."
            )

        new_content = content.replace(target, replacement, 1)
        file_path.write_text(new_content, encoding="utf-8")
        return f"Successfully updated {path_str}"

    return await asyncio.to_thread(_perform_edit)
