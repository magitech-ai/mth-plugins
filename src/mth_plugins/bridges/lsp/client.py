"""Async Language Server Protocol (LSP) stdio JSON-RPC 2.0 client."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LspClient:
    """Async stdio JSON-RPC 2.0 client managing a language server subprocess."""

    def __init__(
        self,
        command: list[str],
        workspace_root: Path,
        language_id: str,
    ) -> None:
        self.command = command
        self.workspace_root = workspace_root
        self.language_id = language_id
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id = 1
        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._latest_diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._diagnostic_events: dict[str, asyncio.Event] = {}
        self._doc_versions: dict[str, int] = {}
        self._closed = False

    async def start(self) -> bool:
        """Starts language server subprocess and performs LSP handshake."""
        if self._process is not None:
            return True

        binary = self.command[0]
        if not shutil.which(binary):
            return False

        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(self.workspace_root),
            )
            self._reader_task = asyncio.create_task(self._read_loop())

            init_params = {
                "processId": os.getpid(),
                "rootUri": self.workspace_root.resolve().as_uri(),
                "capabilities": {
                    "textDocument": {
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "versionSupport": True,
                        },
                        "definition": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                    }
                },
            }
            await self.send_request("initialize", init_params, timeout=5.0)
            await self.send_notification("initialized", {})
            return True
        except (OSError, RuntimeError, TimeoutError):
            await self.stop()
            return False

    async def send_request(self, method: str, params: Any, timeout: float = 5.0) -> Any:
        """Sends a JSON-RPC request and awaits the result."""
        if self._process is None or self._process.stdin is None or self._closed:
            raise RuntimeError("LSP client process not running")

        req_id = self._next_id
        self._next_id += 1

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending_requests[req_id] = future

        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        payload = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")

        try:
            self._process.stdin.write(header + payload)
            await self._process.stdin.drain()
            return await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self._pending_requests.pop(req_id, None)
            raise

    async def send_notification(self, method: str, params: Any) -> None:
        """Sends a JSON-RPC notification (no response expected)."""
        if self._process is None or self._process.stdin is None or self._closed:
            return

        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        payload = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        try:
            self._process.stdin.write(header + payload)
            await self._process.stdin.drain()
        except OSError:
            pass

    async def notify_document(self, file_path: Path, text: str) -> None:
        """Sends didOpen or didChange notification for a document."""
        uri = file_path.resolve().as_uri()
        if uri not in self._doc_versions:
            self._doc_versions[uri] = 1
            await self.send_notification(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": self.language_id,
                        "version": 1,
                        "text": text,
                    }
                },
            )
        else:
            self._doc_versions[uri] += 1
            version = self._doc_versions[uri]
            await self.send_notification(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )

    async def wait_for_diagnostics(
        self, uri: str, debounce_ms: int = 150, timeout_ms: int = 3000
    ) -> list[dict[str, Any]]:
        """Waits for debounced diagnostics published for the specified URI."""
        event = self._diagnostic_events.setdefault(uri, asyncio.Event())
        event.clear()

        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)
        debounce_sec = debounce_ms / 1000.0

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(
                    event.wait(), timeout=min(remaining, debounce_sec * 2)
                )
                event.clear()
                await asyncio.sleep(debounce_sec)
                if not event.is_set():
                    break
            except TimeoutError:
                break

        return self._latest_diagnostics.get(uri, [])

    async def get_definition(self, file_path: Path, line: int, character: int) -> Any:
        """Requests symbol definition location from language server."""
        uri = file_path.resolve().as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }
        return await self.send_request("textDocument/definition", params)

    async def get_references(
        self, file_path: Path, line: int, character: int
    ) -> list[dict[str, Any]]:
        """Requests symbol references from language server."""
        uri = file_path.resolve().as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        }
        res = await self.send_request("textDocument/references", params)
        return res if isinstance(res, list) else []

    async def _read_loop(self) -> None:
        """Reads framed JSON-RPC messages from stdout."""
        if self._process is None or self._process.stdout is None:
            return

        stdout = self._process.stdout
        while not self._closed:
            try:
                line = await stdout.readline()
                if not line:
                    break

                if line.startswith(b"Content-Length:"):
                    parts = line.decode("ascii").split(":")
                    length = int(parts[1].strip())

                    # Skip empty delimiter lines
                    while True:
                        delimiter = await stdout.readline()
                        if delimiter in (b"\r\n", b"\n", b""):
                            break

                    body = await stdout.readexactly(length)
                    data = json.loads(body.decode("utf-8"))
                    self._dispatch_message(data)
            except (asyncio.CancelledError, OSError, ValueError):
                break

    def _dispatch_message(self, msg: dict[str, Any]) -> None:
        """Dispatches an incoming parsed JSON-RPC message."""
        # Request response
        if "id" in msg and ("result" in msg or "error" in msg):
            req_id = msg["id"]
            if req_id in self._pending_requests:
                future = self._pending_requests.pop(req_id)
                if not future.done():
                    if "error" in msg:
                        future.set_exception(RuntimeError(f"LSP error: {msg['error']}"))
                    else:
                        future.set_result(msg.get("result"))
            return

        # Notification
        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params", {})
            uri = params.get("uri")
            diagnostics = params.get("diagnostics", [])
            if uri:
                self._latest_diagnostics[uri] = diagnostics
                event = self._diagnostic_events.setdefault(uri, asyncio.Event())
                event.set()

    async def stop(self) -> None:
        """Shuts down client and terminates subprocess."""
        self._closed = True
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self._process:
            try:
                await self.send_notification("exit", {})
                self._process.terminate()
                await self._process.wait()
            except Exception:
                pass
            self._process = None
