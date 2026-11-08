"""Unit tests for async LspClient stdio JSON-RPC 2.0 communication."""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mth_plugins.bridges.lsp.client import LspClient


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.asyncio
async def test_lsp_client_start_not_on_path(workspace: Path) -> None:
    client = LspClient(["nonexistent-langserver-binary"], workspace, "python")
    with patch("shutil.which", return_value=None):
        started = await client.start()
        assert started is False


@pytest.mark.asyncio
async def test_lsp_client_start_already_running(workspace: Path) -> None:
    client = LspClient(["fake-server"], workspace, "python")
    client._process = MagicMock()
    assert await client.start() is True


@pytest.mark.asyncio
async def test_lsp_client_start_handshake_success(workspace: Path) -> None:
    client = LspClient(["pyright-langserver", "--stdio"], workspace, "python")

    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = asyncio.StreamReader()

    with (
        patch("shutil.which", return_value="/bin/pyright-langserver"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)),
        patch.object(
            client, "send_request", new=AsyncMock(return_value={"capabilities": {}})
        ),
        patch.object(client, "send_notification", new=AsyncMock()),
    ):
        started = await client.start()
        assert started is True
        assert client._process is mock_proc

    await client.stop()


@pytest.mark.asyncio
async def test_lsp_client_start_handshake_failure(workspace: Path) -> None:
    client = LspClient(["pyright-langserver", "--stdio"], workspace, "python")
    with (
        patch("shutil.which", return_value="/bin/pyright-langserver"),
        patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=OSError("Exec failed")),
        ),
    ):
        started = await client.start()
        assert started is False


@pytest.mark.asyncio
async def test_lsp_client_send_request_and_response(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")

    # 1. Not running -> raises
    with pytest.raises(RuntimeError, match="not running"):
        await client.send_request("foo", {})

    # 2. Running
    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_proc.stdin = mock_stdin
    client._process = mock_proc

    # Simulate response coming in
    async def _send() -> Any:
        return await client.send_request("custom/req", {"param": 1}, timeout=2.0)

    task = asyncio.create_task(_send())
    await asyncio.sleep(0.01)

    assert 1 in client._pending_requests
    client._dispatch_message({"jsonrpc": "2.0", "id": 1, "result": {"data": "ok"}})

    res = await task
    assert res == {"data": "ok"}


@pytest.mark.asyncio
async def test_lsp_client_send_request_error_response(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    client._process = mock_proc

    async def _send() -> Any:
        return await client.send_request("bad/req", {}, timeout=2.0)

    task = asyncio.create_task(_send())
    await asyncio.sleep(0.01)

    client._dispatch_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
    )

    with pytest.raises(RuntimeError, match="LSP error"):
        await task


@pytest.mark.asyncio
async def test_lsp_client_send_notification(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    # Not running -> safe no-op
    await client.send_notification("test/notif", {})

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    client._process = mock_proc

    await client.send_notification("test/notif", {"a": 1})
    mock_proc.stdin.write.assert_called_once()

    # Stdin drain raises OSError
    mock_proc.stdin.drain = AsyncMock(side_effect=OSError("Pipe broken"))
    await client.send_notification("test/notif", {"a": 2})  # Safe no-op


@pytest.mark.asyncio
async def test_lsp_client_document_sync_and_diagnostics(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    client._process = mock_proc

    file_p = workspace / "test.py"
    file_p.write_text("x = 1\n", encoding="utf-8")

    # 1. First notify -> didOpen
    await client.notify_document(file_p, "x = 1\n")
    uri = file_p.resolve().as_uri()
    assert client._doc_versions[uri] == 1

    # 2. Second notify -> didChange
    await client.notify_document(file_p, "x = 2\n")
    assert client._doc_versions[uri] == 2

    # 3. Simulate publishDiagnostics notification arriving while waiting
    diags = [
        {
            "range": {"start": {"line": 0, "character": 0}},
            "message": "Undefined variable",
        }
    ]

    async def _publish_later() -> None:
        await asyncio.sleep(0.01)
        client._dispatch_message(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diags},
            }
        )

    pub_task = asyncio.create_task(_publish_later())
    received = await client.wait_for_diagnostics(uri, debounce_ms=10, timeout_ms=500)
    await pub_task
    assert received == diags

    # 4. Immediate deadline timeout
    assert await client.wait_for_diagnostics(uri, timeout_ms=-1) == diags

    # 5. Normal timeout when no event arrives
    assert await client.wait_for_diagnostics("file:///empty.py", timeout_ms=20) == []

    # 6. Secondary event arrives during debounce sleep
    event_loop = asyncio.get_running_loop()
    event_loop.call_later(0.015, client._diagnostic_events[uri].set)
    pub_task2 = asyncio.create_task(_publish_later())
    res_debounce = await client.wait_for_diagnostics(
        uri, debounce_ms=30, timeout_ms=500
    )
    await pub_task2
    assert res_debounce == diags


@pytest.mark.asyncio
async def test_lsp_client_definition_and_references(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    client._process = mock_proc

    file_p = workspace / "main.py"

    with patch.object(
        client,
        "send_request",
        new=AsyncMock(
            side_effect=[
                {"uri": "file:///main.py", "range": {}},
                [{"uri": "file:///main.py"}],
            ]
        ),
    ):
        def_res = await client.get_definition(file_p, 10, 5)
        assert def_res["uri"] == "file:///main.py"

        ref_res = await client.get_references(file_p, 10, 5)
        assert len(ref_res) == 1


@pytest.mark.asyncio
async def test_lsp_client_reader_cancellation(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    mock_proc = MagicMock()
    mock_proc.stdout = asyncio.StreamReader()  # Stays open, blocked on readline
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()
    client._process = mock_proc

    client._reader_task = asyncio.create_task(client._read_loop())
    await asyncio.sleep(0.01)

    # Cancel reader via stop()
    await client.stop()
    assert client._closed is True


@pytest.mark.asyncio
async def test_lsp_client_read_loop_eof(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")
    mock_proc = MagicMock()
    mock_proc.stdout = asyncio.StreamReader()
    mock_proc.stdin = MagicMock()
    client._process = mock_proc
    task = asyncio.create_task(client._read_loop())
    mock_proc.stdout.feed_eof()
    await task


@pytest.mark.asyncio
async def test_lsp_client_read_loop_and_stop(workspace: Path) -> None:
    client = LspClient(["server"], workspace, "python")

    # When process is None -> read_loop returns immediately
    await client._read_loop()

    mock_proc = MagicMock()
    mock_stdout = asyncio.StreamReader()
    mock_proc.stdout = mock_stdout
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()
    client._process = mock_proc

    # Add a pending request to verify cancellation during stop
    pending_fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    client._pending_requests[99] = pending_fut

    # Add an already done future
    done_fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    done_fut.set_result("done")
    client._pending_requests[100] = done_fut

    client._reader_task = asyncio.create_task(client._read_loop())

    # Feed non-header line then extra header line
    mock_stdout.feed_data(b"Log info line\r\n")

    msg = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": "file:///a.py", "diagnostics": []},
        }
    ).encode("utf-8")
    header = (
        f"Content-Length: {len(msg)}\r\nContent-Type: application/json\r\n\r\n".encode(
            "ascii"
        )
    )
    mock_stdout.feed_data(header + msg)

    # Dispatch to done future and unsolicited
    client._pending_requests[101] = done_fut
    client._dispatch_message({"jsonrpc": "2.0", "id": 101, "result": "already_done"})
    client._dispatch_message({"jsonrpc": "2.0", "id": 9999, "result": "unsolicited"})
    client._dispatch_message({"jsonrpc": "2.0", "method": "other/method", "params": {}})
    client._dispatch_message(
        {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {}}
    )

    await asyncio.sleep(0.05)
    assert "file:///a.py" in client._latest_diagnostics

    # Feed data while closed to terminate while loop condition
    client._closed = True
    mock_stdout.feed_data(b"Log line after closed\r\n")
    await asyncio.sleep(0.02)

    # Stop client
    await client.stop()
    assert client._closed is True
    assert client._process is None
    assert pending_fut.cancelled()
