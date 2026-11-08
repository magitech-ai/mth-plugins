"""Unit tests for session search plugin and tool execution."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anima import Context
from magitech_harness.tools.service import ToolService

from mth_plugins.sessions.search.plugin import apply


@pytest.mark.asyncio
async def test_session_search_plugin_and_tool(tmp_path: Path) -> None:
    ctx = Context()
    tools = ToolService(ctx)

    db_path = tmp_path / "search.db"
    service = apply(ctx, db_path=db_path)
    assert service is not None

    tool = tools.get("session_search")
    assert tool is not None

    # Write a test log
    log_file = tmp_path / "chat.jsonl"
    log_file.write_text(
        json.dumps(
            {
                "seq": 1,
                "type": "user/message",
                "timestamp": "2026-11-08T00:00:00Z",
                "payload": {"text": "How do I configure nginx reverse proxy?"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Trigger turn finish event
    mock_session = SimpleNamespace(storage_path=log_file)
    ctx.emit("turn/finish", mock_session, "turn-1")

    # Turn finish with no storage_path
    ctx.emit("turn/finish", SimpleNamespace(storage_path=None), "turn-2")

    # Execute session_search tool
    res = await tool.execute({"query": "nginx reverse proxy", "limit": 5})
    assert res["success"] is True
    assert res["count"] == 1
    assert res["matches"][0]["conversation_id"] == "chat"

    # Context without tools
    empty_ctx = Context()
    svc2 = apply(empty_ctx, db_path=tmp_path / "search2.db")
    assert svc2 is not None

    service.close()
    svc2.close()
