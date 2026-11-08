"""Filesystem tool handler for editing files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


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
