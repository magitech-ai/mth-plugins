"""JSON-RPC 2.0 protocol schemas and serializer for MCP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class JsonRpcError(Exception):
    """Exception representing a JSON-RPC 2.0 error response."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC Error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class JsonRpcRequest:
    """Represents a JSON-RPC 2.0 request."""

    id: int | str
    method: str
    params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass(frozen=True)
class JsonRpcNotification:
    """Represents a JSON-RPC 2.0 notification (no ID)."""

    method: str
    params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass(frozen=True)
class JsonRpcResponse:
    """Represents a JSON-RPC 2.0 response."""

    id: int | str | None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


JsonRpcMessage = JsonRpcRequest | JsonRpcNotification | JsonRpcResponse


def parse_message(data: str | dict[str, Any]) -> JsonRpcMessage:
    """Parses a JSON string or dictionary into a typed JSON-RPC 2.0 message."""
    if isinstance(data, str):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON-RPC payload string: {e}") from e
    else:
        payload = data
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise ValueError("Invalid JSON-RPC 2.0 payload format.")

    if "method" in payload:
        if "id" in payload:
            return JsonRpcRequest(
                id=payload["id"],
                method=payload["method"],
                params=payload.get("params"),
            )
        return JsonRpcNotification(
            method=payload["method"],
            params=payload.get("params"),
        )

    return JsonRpcResponse(
        id=payload.get("id"),
        result=payload.get("result"),
        error=payload.get("error"),
    )


def serialize_message(msg: JsonRpcMessage) -> str:
    """Serializes a JSON-RPC 2.0 message into a JSON string."""
    return json.dumps(msg.to_dict(), separators=(",", ":"))
