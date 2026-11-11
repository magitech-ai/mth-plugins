"""Unit tests for checkpoint bridge component tools and turn waterfall."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from anima import Context
from magitech_harness.tools.service import ToolService

from mth_plugins.bridges.checkpoint.component import apply


@pytest.mark.asyncio
async def test_checkpoint_component_waterfall_and_tools(tmp_path: Path) -> None:
    ctx = Context()
    tools = ToolService(ctx)

    service = apply(
        ctx,
        checkpoints_root=tmp_path / "checkpoints",
        workspace_root=tmp_path / "ws",
    )
    assert service is not None

    # 1. Waterfall execution: captures turn snapshot
    with patch.object(
        service, "capture", AsyncMock(return_value="sha_turn_1")
    ) as mock_cap:
        turn_data = {"turn_id": "turn-101", "user_input": "make edit"}

        async def _default_turn(td: dict[str, Any]) -> str:
            return "Turn finished"

        res = await ctx.waterfall(
            "agent/turn", turn_data, default_handler=_default_turn
        )
        assert res == "Turn finished"
        mock_cap.assert_called_once_with("turn-101")

    # Turn without turn_id: skips capture
    with patch.object(service, "capture", AsyncMock()) as mock_cap_empty:
        await ctx.waterfall("agent/turn", {}, default_handler=_default_turn)
        mock_cap_empty.assert_not_called()

    # 2. Tool checkpoint_diff
    diff_tool = tools.get("checkpoint_diff")
    assert diff_tool is not None
    with patch.object(service, "diff", AsyncMock(return_value="diff output")):
        res_diff = await diff_tool.execute(
            {"target_checkpoint": "t1", "workspace": str(tmp_path / "custom_ws")}
        )
        assert res_diff["success"] is True
        assert res_diff["diff"] == "diff output"

    # 3. Tool checkpoint_restore
    restore_tool = tools.get("checkpoint_restore")
    assert restore_tool is not None
    with patch.object(service, "restore", AsyncMock(return_value=True)):
        res_restore = await restore_tool.execute(
            {"checkpoint_id": "t1", "workspace": str(tmp_path / "custom_ws")}
        )
        assert res_restore["success"] is True
        assert res_restore["checkpoint_id"] == "t1"

    # 4. Context without tools
    empty_ctx = Context()
    s2 = apply(empty_ctx)
    assert s2 is not None
