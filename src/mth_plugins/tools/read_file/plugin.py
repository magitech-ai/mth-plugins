"""Anima plugin entry point for read_file tool."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import define_tool

from mth_plugins.tools.read_file.read_file import handle_read_file


def apply(ctx: Context, **kwargs: Any) -> None:
    """Mounts read_file tool onto ctx.tools."""
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
    ctx.tools.register(read_tool)


apply.inject = ["tools"]  # type: ignore[attr-defined]
