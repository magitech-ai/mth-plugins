"""Filesystem tool handler for writing files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


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
