"""Unit tests for layered ApprovalGuard evaluation and interception."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from anima import Context
from magitech_harness.approval.service import ApprovalRequest, ApprovalService
from magitech_harness.tools.service import ToolCallData

from mth_plugins.guards.approval.guard import ApprovalGuard
from mth_plugins.guards.approval.policy import ApprovalPolicy
from mth_plugins.guards.approval.types import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalScope,
    PolicyRule,
)


@pytest.fixture
def ctx() -> Context:
    context = Context()
    ApprovalService(context)
    return context


@pytest.mark.asyncio
async def test_guard_policy_precedence(ctx: Context, tmp_path: Path) -> None:
    ws_file = tmp_path / "workspace_policy.toml"
    global_file = tmp_path / "global_policy.toml"

    # Workspace allows bash
    ApprovalPolicy(
        [PolicyRule(tool_pattern="bash", outcome=ApprovalOutcome.ALLOW)]
    ).save_rule(ws_file, PolicyRule(tool_pattern="bash", outcome=ApprovalOutcome.ALLOW))
    # Global denies bash
    ApprovalPolicy(
        [PolicyRule(tool_pattern="bash", outcome=ApprovalOutcome.DENY)]
    ).save_rule(
        global_file, PolicyRule(tool_pattern="bash", outcome=ApprovalOutcome.DENY)
    )

    guard = ApprovalGuard(
        ctx=ctx,
        workspace_policy_path=ws_file,
        global_policy_path=global_file,
    )

    req = ApprovalRequest(tool_name="bash", arguments={}, digest="sha256:precedence")
    # Workspace takes precedence -> True
    assert await guard.evaluate_request(req) is True


@pytest.mark.asyncio
async def test_guard_global_fallback(ctx: Context, tmp_path: Path) -> None:
    ws_file = tmp_path / "empty_ws.toml"
    global_file = tmp_path / "global_policy.toml"

    ApprovalPolicy(
        [PolicyRule(tool_pattern="write_file", outcome=ApprovalOutcome.DENY)]
    ).save_rule(
        global_file, PolicyRule(tool_pattern="write_file", outcome=ApprovalOutcome.DENY)
    )

    guard = ApprovalGuard(
        ctx=ctx,
        workspace_policy_path=ws_file,
        global_policy_path=global_file,
    )

    req = ApprovalRequest(
        tool_name="write_file", arguments={}, digest="sha256:fallback"
    )
    assert await guard.evaluate_request(req) is False


@pytest.mark.asyncio
async def test_guard_session_grants_cache(ctx: Context) -> None:
    guard = ApprovalGuard(ctx=ctx)
    guard._session_grants["sha256:cached"] = True

    req = ApprovalRequest(tool_name="custom", arguments={}, digest="sha256:cached")
    assert await guard.evaluate_request(req) is True


@pytest.mark.asyncio
async def test_guard_presenter_handling(ctx: Context, tmp_path: Path) -> None:
    ws_file = tmp_path / "ws.toml"
    guard = ApprovalGuard(ctx=ctx, workspace_policy_path=ws_file)

    # 1. No presenter, no rule -> fails closed
    req1 = ApprovalRequest(tool_name="mutate", arguments={}, digest="sha256:1")
    assert await guard.evaluate_request(req1) is False

    # 2. Presenter throws exception -> fails closed
    failing_presenter = AsyncMock(side_effect=RuntimeError("User closed dialog"))
    guard.set_presenter(failing_presenter)
    assert await guard.evaluate_request(req1) is False

    # 3. Presenter returns invalid object -> fails closed
    invalid_presenter = AsyncMock(return_value={"outcome": "allow"})
    guard.set_presenter(invalid_presenter)
    assert await guard.evaluate_request(req1) is False

    # 4. Presenter returns stale/mismatched digest -> fails closed
    stale_presenter = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.ONCE,
            request_digest="sha256:different",
        )
    )
    guard.set_presenter(stale_presenter)
    assert await guard.evaluate_request(req1) is False

    # 5. Presenter returns DENY -> False
    deny_presenter = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.DENY,
            scope=ApprovalScope.ONCE,
            request_digest="sha256:1",
        )
    )
    guard.set_presenter(deny_presenter)
    assert await guard.evaluate_request(req1) is False

    # 6. Presenter returns ALLOW with ONCE scope -> True, not in session grants
    allow_once = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.ONCE,
            request_digest="sha256:1",
        )
    )
    guard.set_presenter(allow_once)
    assert await guard.evaluate_request(req1) is True
    assert "sha256:1" not in guard._session_grants

    # 7. Presenter returns ALLOW with SESSION scope -> True, cached in session grants
    allow_session = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.SESSION,
            request_digest="sha256:2",
        )
    )
    guard.set_presenter(allow_session)
    req2 = ApprovalRequest(tool_name="mutate", arguments={}, digest="sha256:2")
    assert await guard.evaluate_request(req2) is True
    assert guard._session_grants["sha256:2"] is True

    # 8. Presenter returns ALLOW with PROJECT scope -> True, saved to ws_file
    allow_project = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.PROJECT,
            request_digest="sha256:3",
        )
    )
    guard.set_presenter(allow_project)
    req3 = ApprovalRequest(tool_name="custom_tool", arguments={}, digest="sha256:3")
    assert await guard.evaluate_request(req3) is True
    assert guard._session_grants["sha256:3"] is True
    assert ws_file.is_file()
    assert "custom_tool" in ws_file.read_text(encoding="utf-8")

    # 9. Presenter returns ALLOW with PROJECT scope when workspace_policy_path is None
    # and no approvals service exists.
    empty_ctx = Context()
    no_ws_guard = ApprovalGuard(ctx=empty_ctx, workspace_policy_path=None)
    allow_project_no_ws = AsyncMock(
        return_value=ApprovalDecision(
            outcome=ApprovalOutcome.ALLOW,
            scope=ApprovalScope.PROJECT,
            request_digest="sha256:4",
        )
    )
    no_ws_guard.set_presenter(allow_project_no_ws)
    req4 = ApprovalRequest(tool_name="tool4", arguments={}, digest="sha256:4")
    assert await no_ws_guard.evaluate_request(req4) is True
    assert no_ws_guard._session_grants["sha256:4"] is True


@pytest.mark.asyncio
async def test_guard_tool_pre_execute_interception(ctx: Context) -> None:
    guard = ApprovalGuard(ctx=ctx, require_all_mutations=True)

    next_mock = AsyncMock(return_value="executed")

    # 1. Safe read tool -> passes directly without approval call
    read_call = ToolCallData(
        call_id="c1", name="read_file", arguments={"path": "a.txt"}
    )
    res = await guard.handle_tool_pre_execute(read_call, next_mock)
    assert res == "executed"
    next_mock.assert_awaited_once_with(read_call)

    # 2. Mutating tool when approval service denies -> PermissionError
    next_mock.reset_mock()
    write_call = ToolCallData(
        call_id="c2", name="write_file", arguments={"path": "a.txt"}
    )
    # Default verdict on ApprovalService is False
    with pytest.raises(PermissionError, match="Approval denied"):
        await guard.handle_tool_pre_execute(write_call, next_mock)
    next_mock.assert_not_called()

    # 3. Mutating tool when approval service grants -> executes
    approvals_svc: ApprovalService = ctx.approvals
    approvals_svc.default_verdict = True
    res2 = await guard.handle_tool_pre_execute(write_call, next_mock)
    assert res2 == "executed"
    next_mock.assert_awaited_once_with(write_call)

    # 4. Context without approvals service -> passes through
    empty_ctx = Context()
    no_auth_guard = ApprovalGuard(ctx=empty_ctx)
    next_mock.reset_mock()
    res3 = await no_auth_guard.handle_tool_pre_execute(write_call, next_mock)
    assert res3 == "executed"
