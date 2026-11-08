"""Anima plugin entry point for write_file tool."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import define_tool

from mth_plugins.tools.write_file.write_file import handle_write_file


def apply(ctx: Context, **kwargs: Any) -> None:
    """Mounts write_file tool onto ctx.tools."""
    write_tool = define_tool(
        name="write_file",
        description="Write text content to a file, creating parent directories.",
        parameters={
            "path": {
                "type": "string",
                "description": "Target file path",
                "required": True,
            },
            "content": {
                "type": "string",
                "description": "File content",
                "required": True,
            },
        },
        execute=handle_write_file,
    )
    ctx.tools.register(write_tool)


apply.inject = ["tools"]  # type: ignore[attr-defined]
