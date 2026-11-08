"""Unit tests for MCP transports (Stdio and SSE)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mth_plugins.bridges.mcp.transport import SseTransport, StdioTransport


async def test_stdio_transport_lifecycle() -> None:
    transport = StdioTransport(
        command="python3",
        args=["-c", "import sys; sys.stdout.write(sys.stdin.readline())"],
        env={"TEST_VAR": "1"},
    )
    await transport.start()
    assert transport.process is not None

    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    await transport.send_message(msg)

    received = await transport.receive_message()
    assert received == msg

    await transport.close()
    assert transport.process is None
    # Calling close again is safe
    await transport.close()


async def test_stdio_transport_not_running_raises() -> None:
    transport = StdioTransport("echo")
    with pytest.raises(RuntimeError, match="not running"):
        await transport.send_message({"jsonrpc": "2.0"})

    with pytest.raises(RuntimeError, match="not running"):
        await transport.receive_message()


async def test_stdio_transport_eof_raises() -> None:
    transport = StdioTransport("python3", ["-c", "import sys; sys.exit(0)"])
    await transport.start()
    assert transport.process is not None
    await transport.process.wait()

    with pytest.raises(EOFError):
        await transport.receive_message()
    await transport.close()


async def test_stdio_transport_close_kill_fallback() -> None:
    transport = StdioTransport("sleep", ["10"])
    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.is_closing.return_value = False
    mock_proc.stdin.close.side_effect = OSError("pipe error")

    # simulate wait timing out on terminate, and wait raising ProcessLookupError on kill
    mock_proc.wait = AsyncMock(side_effect=[TimeoutError(), ProcessLookupError()])
    mock_proc.terminate = MagicMock(side_effect=ProcessLookupError())
    mock_proc.kill = MagicMock()

    transport.process = mock_proc
    await transport.close()
    mock_proc.kill.assert_called_once()


async def test_sse_transport_lifecycle() -> None:
    # Mock httpx AsyncClient
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Simulate SSE lines
    sse_lines = [
        ":keepalive comment\n",
        "id: msg-1\n",
        "event: endpoint\n",
        "data: https://api.example.com/messages?sessionId=abc\n",
        "\n",
        "event: message\n",
        "data: not-valid-json\n",
        'data: {"jsonrpc": "2.0", "id": 1, "result": "ok"}\n',
        "\n",
    ]

    class _Response:
        async def aiter_lines(self) -> Any:
            for line in sse_lines:
                yield line

    class _StreamContext:
        async def __aenter__(self) -> Any:
            return _Response()

        async def __aexit__(self, *a: Any) -> None:
            pass

    mock_client.stream = MagicMock(return_value=_StreamContext())
    mock_client.post.return_value = MagicMock(
        status_code=200, raise_for_status=lambda: None
    )

    transport = SseTransport(
        url="https://api.example.com/sse",
        headers={"Authorization": "Bearer test"},
        client=mock_client,
    )

    await transport.start()
    # Allow background listen task to process SSE lines
    await asyncio.sleep(0.05)

    assert transport._post_endpoint == "https://api.example.com/messages?sessionId=abc"

    msg = await transport.receive_message()
    assert msg == {"jsonrpc": "2.0", "id": 1, "result": "ok"}

    # Test send_message
    out_msg: dict[str, Any] = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    await transport.send_message(out_msg)
    mock_client.post.assert_awaited_with(
        "https://api.example.com/messages?sessionId=abc", json=out_msg
    )

    await transport.close()
    assert transport._listener_task is None


async def test_sse_transport_hanging_cancellation() -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    class _HangingResponse:
        async def aiter_lines(self) -> Any:
            while True:
                await asyncio.sleep(10)
                yield ""

    class _StreamContext:
        async def __aenter__(self) -> Any:
            return _HangingResponse()

        async def __aexit__(self, *a: Any) -> None:
            pass

    mock_client.stream = MagicMock(return_value=_StreamContext())
    transport = SseTransport(url="https://api.example.com/sse", client=mock_client)
    await transport.start()
    await asyncio.sleep(0.01)

    # Closing while hanging triggers CancelledError in _listener_task
    await transport.close()
    assert transport._listener_task is None


async def test_sse_transport_not_running_raises() -> None:
    transport = SseTransport(url="https://api.example.com/sse")
    await transport.close()
    with pytest.raises(RuntimeError, match="not running"):
        await transport.send_message({"jsonrpc": "2.0"})


async def test_sse_transport_owns_client_and_stream_error() -> None:
    transport = SseTransport(url="https://api.example.com/sse")
    assert transport._owns_client is True

    # Mock httpx.AsyncClient created inside start()
    mock_inner_client = AsyncMock(spec=httpx.AsyncClient)
    # Simulate stream throwing an exception
    mock_inner_client.stream.side_effect = RuntimeError("Network error")
    mock_inner_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_inner_client):
        await transport.start()
        await asyncio.sleep(0.02)
        await transport.close()
        mock_inner_client.aclose.assert_awaited_once()


async def test_stdio_transport_close_edges() -> None:
    # 1. Close when process is None
    transport1 = StdioTransport("echo")
    await transport1.close()

    # 2. Close when stdin is None and returncode is 0 (already finished)
    transport2 = StdioTransport("echo")
    mock_proc = AsyncMock()
    mock_proc.stdin = None
    mock_proc.returncode = 0
    transport2.process = mock_proc
    await transport2.close()
    assert transport2.process is None
