"""Anima plugin entry point for filesystem tools."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import define_tool

from mth_plugins.tools.fs.fs import (
    handle_edit_file,
    handle_read_file,
    handle_write_file,
)


def apply(ctx: Context, **kwargs: Any) -> None:
    """Mounts read_file, write_file, and edit_file tools onto ctx.tools."""
    read_tool = define_tool(
        name="read_file",
        description="Read file contents with line offset and limit pagination.",
        parameters={
            "path": {"type": "string", "description": "Path to file", "required": True},
            "offset": {"type": "integer", "description": "1-indexed starting line"},
            "limit": {"type": "integer", "description": "Maximum lines to read"},
        },
        execute=handle_read_file,
    )
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
    edit_tool = define_tool(
        name="edit_file",
        description="Replace target string with replacement string in a file.",
        parameters={
            "path": {
                "type": "string",
                "description": "Target file path",
                "required": True,
            },
            "target": {
                "type": "string",
                "description": "Exact text to replace",
                "required": True,
            },
            "replacement": {
                "type": "string",
                "description": "Replacement text",
                "required": True,
            },
        },
        execute=handle_edit_file,
    )

    ctx.tools.register(read_tool)
    ctx.tools.register(write_tool)
    ctx.tools.register(edit_tool)


apply.inject = ["tools"]  # type: ignore[attr-defined]
