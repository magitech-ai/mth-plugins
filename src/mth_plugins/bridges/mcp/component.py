"""Anima component entry point for mcp-bridge."""

from __future__ import annotations

from typing import Any

from anima import Context

from mth_plugins.bridges.mcp.service import McpBridgeService


async def apply(
    ctx: Context,
    config_file: str = "mcp.json",
    auto_load: bool = True,
    **kwargs: Any,
) -> None:
    """Anima component mounting McpBridgeService and loading configured servers."""
    ctx.use(McpBridgeService)
    await ctx.flush()

    if auto_load and ctx.has("mcp"):
        service: McpBridgeService = ctx.mcp
        await service.load_from_layers(config_file)
