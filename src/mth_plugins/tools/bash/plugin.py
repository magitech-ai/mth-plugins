"""Anima plugin entry point for bash tool."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import define_tool

from mth_plugins.tools.bash.bash import handle_bash


def apply(ctx: Context, **kwargs: Any) -> None:
    """Mounts bash tool onto ctx.tools."""
    bash_tool = define_tool(
        name="bash",
        description="Execute a bash command in a subprocess.",
        parameters={
            "command": {
                "type": "string",
                "description": "Shell command to execute",
                "required": True,
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Timeout in milliseconds (default 30000)",
            },
            "cwd": {
                "type": "string",
                "description": "Optional working directory",
            },
        },
        execute=handle_bash,
    )
    ctx.tools.register(bash_tool)


apply.inject = ["tools"]  # type: ignore[attr-defined]
