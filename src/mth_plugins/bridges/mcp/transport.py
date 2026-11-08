"""Transports for Model Context Protocol communication."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

import httpx

logger = logging.getLogger("mth_plugins.bridges.mcp")


class McpTransport(ABC):
    """Abstract base transport for bidirectional JSON-RPC message exchange."""

    @abstractmethod
    async def start(self) -> None:
        """Initializes the transport connection."""

    @abstractmethod
    async def send_message(self, msg: dict[str, Any]) -> None:
        """Sends a JSON-RPC message dictionary over the transport."""

    @abstractmethod
    async def receive_message(self) -> dict[str, Any]:
        """Awaits and returns the next JSON-RPC message dictionary."""

    @abstractmethod
    async def close(self) -> None:
        """Terminates transport connection and frees associated resources."""


class StdioTransport(McpTransport):
    """Subprocess standard I/O transport for MCP servers."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: Path | str | None = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = str(cwd) if cwd else None
        self.process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """Spawns the target process with piped stdio."""
        environ = dict(os.environ)
        if self.env:
            environ.update(self.env)

        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environ,
            cwd=self.cwd,
        )

    async def send_message(self, msg: dict[str, Any]) -> None:
        """Encodes and writes a single JSON line to subprocess stdin."""
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("StdioTransport process is not running.")
        line = json.dumps(msg, separators=(",", ":")) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def receive_message(self) -> dict[str, Any]:
        """Reads a single JSON line from subprocess stdout."""
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("StdioTransport process is not running.")
        line_bytes = await self.process.stdout.readline()
        if not line_bytes:
            raise EOFError("StdioTransport stream reached EOF.")
        return cast(dict[str, Any], json.loads(line_bytes.decode("utf-8").strip()))

    async def close(self) -> None:
        """Closes standard streams and terminates child process."""
        if self.process is None:
            return
        if self.process.stdin is not None and not self.process.stdin.is_closing():
            try:
                self.process.stdin.close()
                await self.process.stdin.wait_closed()
            except Exception:
                pass

        if self.process.returncode is None:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except (TimeoutError, ProcessLookupError, Exception):
                try:
                    self.process.kill()
                    await self.process.wait()
                except (ProcessLookupError, Exception):
                    pass
        self.process = None


class SseTransport(McpTransport):
    """Server-Sent Events (SSE) and HTTP POST transport for remote MCP servers."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self._client = client
        self._owns_client = client is None
        self._post_endpoint: str | None = None
        self._incoming_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Connects to SSE stream and resolves POST message endpoint."""
        if self._client is None:
            self._client = httpx.AsyncClient(headers=self.headers, timeout=30.0)

        # In standard MCP over SSE: GET {url} streams 'event: endpoint' or messages
        self._post_endpoint = self.url
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """Background loop reading SSE stream."""
        assert self._client is not None
        try:
            async with self._client.stream("GET", self.url) as response:
                current_event = "message"
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()
                        if current_event == "endpoint":
                            self._post_endpoint = data_str
                        else:
                            try:
                                msg = json.loads(data_str)
                                await self._incoming_queue.put(msg)
                            except json.JSONDecodeError:
                                pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("SSE stream connection ended: %s", e)

    async def send_message(self, msg: dict[str, Any]) -> None:
        """Sends a JSON-RPC message via HTTP POST to the resolved endpoint."""
        if self._client is None:
            raise RuntimeError("SseTransport is not running.")
        target_url = self._post_endpoint or self.url
        resp = await self._client.post(target_url, json=msg)
        resp.raise_for_status()

    async def receive_message(self) -> dict[str, Any]:
        """Fetches the next message from the SSE incoming queue."""
        return await self._incoming_queue.get()

    async def close(self) -> None:
        """Cancels listener task and closes HTTP client."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
