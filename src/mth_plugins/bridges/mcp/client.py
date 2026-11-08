"""High-level client for Model Context Protocol JSON-RPC interactions."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from mth_plugins.bridges.mcp.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_message,
)
from mth_plugins.bridges.mcp.transport import McpTransport


class McpClient:
    """Client managing an MCP session across a pluggable transport."""

    def __init__(
        self,
        transport: McpTransport,
        server_name: str = "default",
    ) -> None:
        self.transport = transport
        self.server_name = server_name
        self._req_counter = 0
        self._pending_requests: dict[int | str, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    async def connect(self) -> dict[str, Any]:
        """Initializes transport and completes MCP handshake."""
        await self.transport.start()
        self._reader_task = asyncio.create_task(self._reader_loop())

        # Handshake: initialize request
        init_req = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": f"magitech-{self.server_name}",
                "version": "0.1.0",
            },
        }
        res = await self.send_request("initialize", init_req)

        # Handshake: initialized notification
        notif = JsonRpcNotification(method="notifications/initialized")
        await self.transport.send_message(notif.to_dict())
        return res

    async def _reader_loop(self) -> None:
        """Background listener reading inbound messages from transport."""
        try:
            while not self._closed:
                try:
                    raw_msg = await self.transport.receive_message()
                except asyncio.CancelledError:
                    raise
                except (EOFError, Exception):
                    break

                try:
                    msg = parse_message(raw_msg)
                except ValueError:
                    continue

                if isinstance(msg, JsonRpcResponse) and msg.id is not None:
                    fut = self._pending_requests.pop(msg.id, None)
                    if fut is not None and not fut.done():
                        if msg.error is not None:
                            fut.set_exception(
                                JsonRpcError(
                                    code=msg.error.get("code", -32000),
                                    message=msg.error.get("message", "Unknown error"),
                                    data=msg.error.get("data"),
                                )
                            )
                        else:
                            fut.set_result(msg.result or {})
        finally:
            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.cancel()
            self._pending_requests.clear()

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Sends a JSON-RPC request and awaits the correlated response."""
        if self._closed:
            raise RuntimeError("McpClient is closed.")

        req_id = self._next_id()
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = fut

        req = JsonRpcRequest(id=req_id, method=method, params=params)
        await self.transport.send_message(req.to_dict())
        return await fut

    async def list_tools(self) -> list[dict[str, Any]]:
        """Queries the MCP server for advertised tool schemas."""
        res = await self.send_request("tools/list", {})
        return cast(list[dict[str, Any]], res.get("tools", []))

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Executes a tool call on the remote server and formats returned content."""
        res = await self.send_request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

        content_items = res.get("content", [])
        text_parts: list[str] = []
        for item in content_items:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                text_parts.append(item)

        result_text = "\n".join(text_parts) if text_parts else str(res)
        if res.get("isError"):
            return f"Error: {result_text}"
        return result_text

    async def close(self) -> None:
        """Closes reader loop and underlying transport."""
        if self._closed:
            return
        self._closed = True

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        await self.transport.close()
