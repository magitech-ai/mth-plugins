"""Anima component entry point for edit_file tool."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import define_tool

from mth_plugins.tools.edit_file.edit_file import handle_edit_file


def apply(ctx: Context, **kwargs: Any) -> None:
    """Mounts edit_file tool onto ctx.tools."""
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
    ctx.tools.register(edit_tool)


apply.inject = ["tools"]  # type: ignore[attr-defined]
