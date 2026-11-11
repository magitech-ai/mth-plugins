"""Unit tests for MCP component entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from anima import Context

from mth_plugins.bridges.mcp.component import apply


async def test_mcp_component_apply() -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.mcp.service.McpBridgeService.load_from_layers",
        new_callable=AsyncMock,
    ) as mock_load:
        await apply(ctx, config_file="mcp.json", auto_load=True)
        await ctx.flush()

        assert ctx.has("mcp")
        mock_load.assert_awaited_once_with("mcp.json")


async def test_mcp_component_apply_no_auto_load() -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.mcp.service.McpBridgeService.load_from_layers",
        new_callable=AsyncMock,
    ) as mock_load:
        await apply(ctx, config_file="mcp.json", auto_load=False)
        await ctx.flush()

        assert ctx.has("mcp")
        mock_load.assert_not_awaited()
