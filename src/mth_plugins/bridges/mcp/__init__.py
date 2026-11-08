"""Model Context Protocol (MCP) bridge package for Magitech Harness."""

from __future__ import annotations

from mth_plugins.bridges.mcp.client import McpClient
from mth_plugins.bridges.mcp.protocol import (
    JsonRpcError,
    JsonRpcMessage,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
)
from mth_plugins.bridges.mcp.service import McpBridgeService
from mth_plugins.bridges.mcp.transport import (
    McpTransport,
    SseTransport,
    StdioTransport,
)

__all__ = [
    "JsonRpcError",
    "JsonRpcMessage",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpBridgeService",
    "McpClient",
    "McpTransport",
    "SseTransport",
    "StdioTransport",
]
