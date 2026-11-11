"""Unit tests for approval guard component registration and lifecycle."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from anima import Context
from magitech_harness.approval.service import ApprovalRequest, ApprovalService
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolCallData, ToolResultData, ToolService

from mth_plugins.guards.approval.component import apply
from mth_plugins.guards.approval.types import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalScope,
)


@pytest.mark.asyncio
async def test_component_apply_and_waterfalls(tmp_path: Path) -> None:
    ctx = Context()
    ApprovalService(ctx)
    tools = ToolService(ctx)

    # Register a sample tool
    async def sample_exec(args: dict[str, str]) -> str:
        return f"Wrote {args.get('path')}"

    tools.register(
        Tool(
            name="write_file",
            description="Write tool",
            parameters={"path": {"type": "string"}},
            handler=sample_exec,
        )
    )

    # Mount component with an interactive presenter
    presenter_mock = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.SESSION,
            request_digest="sha256:digest",
        )
    )

    apply(
        ctx,
        workspace_root=tmp_path,
        presenter=presenter_mock,
        require_all_mutations=True,
    )

    # 1. Test approval/request waterfall
    req = ApprovalRequest(
        tool_name="write_file", arguments={"path": "foo.txt"}, digest="sha256:digest"
    )
    verdict = await ctx.waterfall(
        "approval/request", req, default_handler=lambda r: False
    )
    assert verdict is True
    presenter_mock.assert_awaited_once()

    # 2. Test denied approval/request
    presenter_deny = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.DENY,
            scope=ApprovalScope.ONCE,
            request_digest="sha256:deny",
        )
    )
    apply(ctx, workspace_root=tmp_path, presenter=presenter_deny)
    req_deny = ApprovalRequest(tool_name="bash", arguments={}, digest="sha256:deny")
    verdict_deny = await ctx.waterfall(
        "approval/request", req_deny, default_handler=lambda r: True
    )
    assert verdict_deny is False

    # 3. Test tools/pre-execute waterfall through ToolService.execute
    # Denied tool execution returns ToolResultData with is_error=True
    call = ToolCallData(
        call_id="c_denied", name="write_file", arguments={"path": "denied.txt"}
    )
    result = await tools.execute(call)
    assert isinstance(result, ToolResultData)
    assert result.is_error is True
    assert "Approval denied" in result.content
