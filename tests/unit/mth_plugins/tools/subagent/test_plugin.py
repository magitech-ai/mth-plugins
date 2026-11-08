"""Unit tests for subagent plugin tool registration and execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from anima import Context
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.subagent.plugin import apply
from mth_plugins.tools.subagent.types import SubagentRecord, SubagentState


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    c = Context()
    c.workspace_dir = tmp_path
    ToolService(c)
    return c


@pytest.mark.asyncio
async def test_subagent_plugin_apply_and_tools(ctx: Context) -> None:
    manager = apply(ctx)
    assert manager is not None
    assert ctx.subagents is manager

    tools_svc: ToolService = ctx.tools
    assert tools_svc.get("invoke_subagent") is not None
    assert tools_svc.get("send_message") is not None
    assert tools_svc.get("manage_subagents") is not None

    # 1. invoke_subagent tool call
    mock_rec = SubagentRecord(
        subagent_id="sub-abc",
        role="tester",
        agent_name="subagent",
        model_id="inherit",
        workspace_path=Path("/tmp"),
        session_id="s1",
        session_path=Path("/tmp/s1.jsonl"),
        state=SubagentState.COMPLETED,
        summary="Invoked ok",
    )
    with patch.object(manager, "invoke", AsyncMock(return_value=[mock_rec])):
        res_inv = await tools_svc.get("invoke_subagent").execute(
            {
                "role": "tester",
                "prompt": "run tests",
                "workspace": "branch",
                "allowed_tools": ["read_file"],
            }
        )
        assert res_inv["success"] is True
        assert len(res_inv["subagents"]) == 1
        assert res_inv["subagents"][0]["subagent_id"] == "sub-abc"

    # 2. send_message tool call
    with patch.object(manager, "send_message", AsyncMock(return_value=mock_rec)):
        res_msg = await tools_svc.get("send_message").execute(
            {"subagent_id": "sub-abc", "message": "status update"}
        )
        assert res_msg["success"] is True
        assert res_msg["subagent"]["subagent_id"] == "sub-abc"

    # 3. manage_subagents tool call
    with patch.object(manager, "manage", AsyncMock(return_value=[mock_rec])):
        res_manage = await tools_svc.get("manage_subagents").execute({"action": "list"})
        assert res_manage["success"] is True
        assert res_manage["action"] == "list"
        assert len(res_manage["subagents"]) == 1


def test_subagent_plugin_apply_without_tools() -> None:
    ctx = Context()
    manager = apply(ctx)
    assert manager is not None
