"""Unit tests for JSON-RPC 2.0 protocol serialization and parsing."""

from __future__ import annotations

import pytest

from mth_plugins.bridges.mcp.protocol import (
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_message,
    serialize_message,
)


def test_json_rpc_error_properties() -> None:
    err = JsonRpcError(-32600, "Invalid Request", data={"details": "bad id"})
    assert err.code == -32600
    assert err.message == "Invalid Request"
    assert err.data == {"details": "bad id"}
    assert "Invalid Request" in str(err)


def test_request_serialization_and_parsing() -> None:
    req = JsonRpcRequest(id=1, method="tools/list", params={"limit": 10})
    serialized = serialize_message(req)
    parsed = parse_message(serialized)

    assert isinstance(parsed, JsonRpcRequest)
    assert parsed.id == 1
    assert parsed.method == "tools/list"
    assert parsed.params == {"limit": 10}

    req_no_params = JsonRpcRequest(id="str-id", method="ping")
    assert req_no_params.to_dict() == {
        "jsonrpc": "2.0",
        "id": "str-id",
        "method": "ping",
    }


def test_notification_serialization_and_parsing() -> None:
    notif = JsonRpcNotification(
        method="notifications/initialized", params={"status": "ready"}
    )
    serialized = serialize_message(notif)
    parsed = parse_message(serialized)

    assert isinstance(parsed, JsonRpcNotification)
    assert parsed.method == "notifications/initialized"
    assert parsed.params == {"status": "ready"}

    notif_no_params = JsonRpcNotification(method="ping")
    assert notif_no_params.to_dict() == {"jsonrpc": "2.0", "method": "ping"}


def test_response_serialization_and_parsing() -> None:
    # Result response
    resp = JsonRpcResponse(id=1, result={"tools": []})
    serialized = serialize_message(resp)
    parsed = parse_message(serialized)

    assert isinstance(parsed, JsonRpcResponse)
    assert parsed.id == 1
    assert parsed.result == {"tools": []}
    assert parsed.error is None

    # Error response
    err_resp = JsonRpcResponse(
        id=2, error={"code": -32601, "message": "Method not found"}
    )
    serialized_err = serialize_message(err_resp)
    parsed_err = parse_message(serialized_err)

    assert isinstance(parsed_err, JsonRpcResponse)
    assert parsed_err.id == 2
    assert parsed_err.error == {"code": -32601, "message": "Method not found"}


def test_invalid_payload_raises() -> None:
    with pytest.raises(ValueError, match=r"Invalid JSON-RPC 2\.0 payload format"):
        parse_message('{"method": "foo"}')  # missing jsonrpc: "2.0"

    with pytest.raises(ValueError, match="Invalid JSON-RPC payload string"):
        parse_message("not-json-dict")
