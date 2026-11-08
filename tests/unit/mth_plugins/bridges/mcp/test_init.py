"""Unit tests for MCP bridge exports."""

from __future__ import annotations

from mth_plugins.bridges import mcp


def test_mcp_exports() -> None:
    assert hasattr(mcp, "McpClient")
    assert hasattr(mcp, "McpBridgeService")
    assert hasattr(mcp, "McpTransport")
    assert hasattr(mcp, "StdioTransport")
    assert hasattr(mcp, "SseTransport")
    assert hasattr(mcp, "JsonRpcRequest")
    assert hasattr(mcp, "JsonRpcResponse")
    assert hasattr(mcp, "JsonRpcNotification")
    assert hasattr(mcp, "JsonRpcError")
