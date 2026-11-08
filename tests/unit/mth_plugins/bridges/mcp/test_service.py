"""Unit tests for McpBridgeService registration and tool mounting."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from anima import Context
from magitech_harness.session.events import ToolCallData
from magitech_harness.tools.service import ToolService

from mth_plugins.bridges.mcp.client import McpClient
from mth_plugins.bridges.mcp.service import McpBridgeService


async def test_service_load_servers_and_tool_registration() -> None:
    ctx = Context()
    ctx.plugin(ToolService)
    await ctx.flush()
    service = McpBridgeService(ctx)

    config = {
        "mcpServers": {
            "demo_stdio": {
                "command": "node",
                "args": ["server.js"],
            },
            "demo_sse": {
                "url": "https://api.example.com/sse",
            },
            "invalid_server": 123,
        }
    }

    mock_client_stdio = AsyncMock(spec=McpClient)
    mock_client_stdio.list_tools.return_value = [
        {
            "name": "calc",
            "description": "Calculates numbers",
            "inputSchema": {"type": "object"},
        }
    ]
    mock_client_stdio.call_tool.return_value = "42"

    mock_client_sse = AsyncMock(spec=McpClient)
    mock_client_sse.list_tools.return_value = [
        {
            "name": "status",
            "description": "Remote server status",
        }
    ]
    mock_client_sse.call_tool.return_value = "healthy"

    with patch(
        "mth_plugins.bridges.mcp.service.McpClient",
        side_effect=[mock_client_stdio, mock_client_sse],
    ):
        loaded = await service.load_servers_from_config(config)
        assert "demo_stdio" in loaded
        assert "demo_sse" in loaded
        assert len(service.clients) == 2

    # Check tools were registered on ctx.tools
    assert ctx.tools.get("mcp_demo_stdio_calc") is not None
    assert ctx.tools.get("mcp_demo_sse_status") is not None

    # Invoke tool handler
    call_data = ToolCallData(
        call_id="call-1",
        name="mcp_demo_stdio_calc",
        arguments={"expr": "6*7"},
    )
    calc_res = await ctx.tools.execute(call_data)
    assert calc_res.content == "42"
    mock_client_stdio.call_tool.assert_awaited_with("calc", {"expr": "6*7"})

    # Close all
    await service.close_all()
    assert ctx.tools.get("mcp_demo_stdio_calc") is None
    assert ctx.tools.get("mcp_demo_sse_status") is None
    assert len(service.clients) == 0


async def test_service_connect_failure_handled() -> None:
    ctx = Context()
    ctx.plugin(ToolService)
    service = McpBridgeService(ctx)

    config = {"mcpServers": {"broken_server": {"command": "broken-cmd"}}}

    mock_client = AsyncMock(spec=McpClient)
    mock_client.connect.side_effect = RuntimeError("Failed to start process")

    with patch("mth_plugins.bridges.mcp.service.McpClient", return_value=mock_client):
        loaded = await service.load_servers_from_config(config)
        assert len(loaded) == 0
        mock_client.close.assert_awaited_once()


async def test_service_load_from_layers(tmp_path: Path) -> None:
    ctx = Context()
    ctx.plugin(ToolService)
    await ctx.flush()
    service = McpBridgeService(ctx)

    mcp_file = tmp_path / "mcp.json"
    mcp_file.write_text(json.dumps({"mcpServers": {"mock": {"command": "mock"}}}))

    bad_file = tmp_path / "bad_mcp.json"
    bad_file.write_text("invalid-json{")

    # Mock ctx.layers
    mock_layers = MagicMock()
    mock_layers.find_all.return_value = [mcp_file, bad_file]
    ctx._register_service("layers", mock_layers)

    mock_client = AsyncMock(spec=McpClient)
    mock_client.list_tools.return_value = []

    with patch("mth_plugins.bridges.mcp.service.McpClient", return_value=mock_client):
        loaded = await service.load_from_layers("mcp.json")
        assert loaded == ["mock"]


async def test_service_unsupported_config_and_nameless_tool() -> None:
    ctx = Context()
    ctx.plugin(ToolService)
    await ctx.flush()
    service = McpBridgeService(ctx)

    # Config with an entry that has neither command nor url
    config = {
        "mcpServers": {
            "unsupported": {"unknown_field": True},
            "valid": {"command": "test"},
        }
    }

    mock_client = AsyncMock(spec=McpClient)
    # List tools with empty name and valid name
    mock_client.list_tools.return_value = [
        {"name": "", "description": "no name"},
        {"name": "valid_tool"},
    ]
    with patch("mth_plugins.bridges.mcp.service.McpClient", return_value=mock_client):
        loaded = await service.load_servers_from_config(config)
        assert loaded == ["valid"]
        assert ctx.tools.get("mcp_valid_valid_tool") is not None


async def test_service_without_tools_or_layers() -> None:
    ctx = Context()
    service = McpBridgeService(ctx)

    # load_from_layers without layers service on ctx
    loaded = await service.load_from_layers("mcp.json")
    assert loaded == []

    # _register_server_tools without tools service on ctx
    mock_client = AsyncMock(spec=McpClient)
    await service._register_server_tools("test", mock_client)
    mock_client.list_tools.assert_not_awaited()


async def test_service_disposer_cleanup_on_fiber_dispose() -> None:
    ctx = Context()
    ctx.plugin(ToolService)
    await ctx.flush()

    fiber = ctx.plugin(McpBridgeService)
    await ctx.flush()
    service: McpBridgeService = ctx.mcp

    mock_client = AsyncMock(spec=McpClient)
    mock_client.list_tools.return_value = [{"name": "tool_x"}]
    with patch("mth_plugins.bridges.mcp.service.McpClient", return_value=mock_client):
        await service.load_servers_from_config(
            {"mcpServers": {"srv": {"command": "x"}}}
        )
        assert ctx.tools.get("mcp_srv_tool_x") is not None

    # Dispose fiber should trigger registered cleanup disposers
    await fiber.dispose()
    assert ctx.tools.get("mcp_srv_tool_x") is None
