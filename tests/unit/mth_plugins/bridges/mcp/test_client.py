"""Unit tests for McpClient session handling."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mth_plugins.bridges.mcp.client import McpClient
from mth_plugins.bridges.mcp.protocol import JsonRpcError
from mth_plugins.bridges.mcp.transport import McpTransport


class MockTransport(McpTransport):
    """In-memory mock transport for testing McpClient."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False

    async def start(self) -> None:
        pass

    async def send_message(self, msg: dict[str, Any]) -> None:
        self.sent.append(msg)
        # If initialize request, auto-reply
        if msg.get("method") == "initialize":
            await self.inbox.put(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"protocolVersion": "2024-11-05"},
                }
            )

    async def receive_message(self) -> dict[str, Any]:
        return await self.inbox.get()

    async def close(self) -> None:
        self.closed = True


async def test_mcp_client_connect_and_handshake() -> None:
    transport = MockTransport()
    client = McpClient(transport, server_name="test")

    res = await client.connect()
    assert res == {"protocolVersion": "2024-11-05"}
    assert len(transport.sent) == 2
    assert transport.sent[0]["method"] == "initialize"
    assert transport.sent[1]["method"] == "notifications/initialized"

    await client.close()
    assert transport.closed is True


async def test_mcp_client_list_tools() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    async def _respond_tools() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echoes text",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            }
        )

    task = asyncio.create_task(_respond_tools())
    tools = await client.list_tools()
    await task
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    await client.close()


async def test_mcp_client_call_tool_formats() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    # 1. Normal text content
    async def _respond_call_normal() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": "result part 1"},
                        "part 2",
                    ]
                },
            }
        )

    task1 = asyncio.create_task(_respond_call_normal())
    res1 = await client.call_tool("echo", {"msg": "hello"})
    await task1
    assert res1 == "result part 1\npart 2"

    # 2. Error response
    async def _respond_call_error() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": "File not found"}],
                },
            }
        )

    task2 = asyncio.create_task(_respond_call_error())
    res2 = await client.call_tool("read", {"file": "missing.txt"})
    await task2
    assert res2 == "Error: File not found"

    await client.close()


async def test_mcp_client_rpc_error() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    async def _respond_error() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": "Method not found"},
            }
        )

    task = asyncio.create_task(_respond_error())
    with pytest.raises(JsonRpcError, match="Method not found"):
        await client.send_request("non_existent")
    await task
    await client.close()


async def test_mcp_client_closed_raises() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.close()
    # Double close is safe
    await client.close()

    with pytest.raises(RuntimeError, match="McpClient is closed"):
        await client.send_request("ping")


async def test_mcp_client_reader_notification_and_bad_message() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    # Deliver a notification (no id)
    await transport.inbox.put({"jsonrpc": "2.0", "method": "custom/notify"})
    # Deliver bad payload (fails parse_message)
    await transport.inbox.put({"invalid": True})
    # Deliver unsolicited response (id not in pending requests)
    await transport.inbox.put({"jsonrpc": "2.0", "id": 9999, "result": "unsolicited"})
    await asyncio.sleep(0.01)

    await client.close()


async def test_mcp_client_reader_eof_and_error() -> None:
    class _EofTransport(MockTransport):
        async def receive_message(self) -> dict[str, Any]:
            raise EOFError()

    c1 = McpClient(_EofTransport())
    with pytest.raises(asyncio.CancelledError):
        await c1.connect()
    await c1.close()

    class _ErrTransport(MockTransport):
        async def receive_message(self) -> dict[str, Any]:
            raise RuntimeError("stream broke")

    c2 = McpClient(_ErrTransport())
    with pytest.raises(asyncio.CancelledError):
        await c2.connect()
    await c2.close()


async def test_mcp_client_pending_future_already_done_on_close() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    loop = asyncio.get_running_loop()
    done_fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    done_fut.set_result({"ok": True})
    client._pending_requests[999] = done_fut

    # Also test closing while reader loop finishes
    client._closed = True
    await transport.inbox.put({"jsonrpc": "2.0", "method": "dummy"})
    await asyncio.sleep(0.01)

    await client.close()


async def test_mcp_client_call_tool_unknown_item_type() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    async def _respond_unknown_item() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [12345]},
            }
        )

    task = asyncio.create_task(_respond_unknown_item())
    res = await client.call_tool("tool", {})
    await task
    assert "12345" in res
    await client.close()


async def test_mcp_client_pending_future_cancelled_on_close() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    # Start a request that won't get answered
    req_task = asyncio.create_task(client.send_request("slow_method"))
    await asyncio.sleep(0.01)

    # Closing client should cancel pending futures
    await client.close()
    with pytest.raises(asyncio.CancelledError):
        await req_task


async def test_mcp_client_call_tool_no_content_fallback() -> None:
    transport = MockTransport()
    client = McpClient(transport)
    await client.connect()

    async def _respond_no_content() -> None:
        await asyncio.sleep(0.01)
        req_id = transport.sent[-1]["id"]
        await transport.inbox.put(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"status": "success"},
            }
        )

    task = asyncio.create_task(_respond_no_content())
    res = await client.call_tool("custom_tool", {})
    await task
    assert "{'status': 'success'}" in res
    await client.close()
