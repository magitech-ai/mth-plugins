"""Unit tests for session title plugin registration and turn waterfall."""

from __future__ import annotations

from typing import Any

import pytest
from anima import Context
from magitech_harness.tools.service import ToolService

from mth_plugins.sessions.title.plugin import apply


@pytest.mark.asyncio
async def test_session_title_plugin_waterfall_and_tool() -> None:
    ctx = Context()
    tools = ToolService(ctx)

    service = apply(ctx)
    assert service is not None
    assert ctx.session_title is service

    # 1. Trigger agent/turn waterfall
    turn_data = {
        "session_id": "conv-101",
        "user_input": "Optimize SQLite FTS5 query performance",
    }

    async def _mock_next(td: dict[str, Any]) -> str:
        return "Turn finished"

    res = await ctx.waterfall("agent/turn", turn_data, default_handler=_mock_next)
    assert res == "Turn finished"
    assert service.get_title("conv-101") == "Optimize SQLite FTS5 query performance"

    # Turn with empty user_input
    turn_empty = {"session_id": "conv-102", "user_input": ""}
    await ctx.waterfall("agent/turn", turn_empty, default_handler=_mock_next)
    assert service.get_title("conv-102") is None

    # 2. set_session_title tool
    tool = tools.get("set_session_title")
    assert tool is not None

    tool_res = await tool.execute(
        {"title": "Custom Renamed Title", "session_id": "conv-101"}
    )
    assert tool_res["success"] is True
    assert tool_res["title"] == "Custom Renamed Title"
    assert service.get_title("conv-101") == "Custom Renamed Title"

    # Context without tools
    empty_ctx = Context()
    s2 = apply(empty_ctx)
    assert s2 is not None
