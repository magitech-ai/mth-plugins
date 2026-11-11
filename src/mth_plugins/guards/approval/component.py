"""Anima component entry point for the approval guardrail."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from anima import Context
from magitech_harness.approval.service import ApprovalRequest
from magitech_harness.tools.service import ToolCallData

from mth_plugins.guards.approval.guard import ApprovalGuard
from mth_plugins.guards.approval.types import ApprovalPresenter


def apply(
    ctx: Context,
    workspace_root: Path | None = None,
    presenter: ApprovalPresenter | None = None,
    require_all_mutations: bool = True,
    **kwargs: Any,
) -> None:
    """Mounts the approval guard onto the Anima context."""
    root = workspace_root or Path.cwd()
    workspace_policy = root / ".agents" / "approval" / "policy.toml"
    global_policy = Path.home() / ".agents" / "approval" / "policy.toml"

    guard = ApprovalGuard(
        ctx=ctx,
        workspace_policy_path=workspace_policy,
        global_policy_path=global_policy,
        presenter=presenter,
        require_all_mutations=require_all_mutations,
    )

    async def _on_approval_request(
        req: ApprovalRequest,
        next_fn: Callable[..., Any],
    ) -> bool:
        verdict = await guard.evaluate_request(req)
        return verdict

    async def _on_tools_pre_execute(
        tool_call: ToolCallData,
        next_fn: Callable[..., Any],
    ) -> Any:
        return await guard.handle_tool_pre_execute(tool_call, next_fn)

    ctx.on("approval/request", _on_approval_request)
    ctx.on("tools/pre-execute", _on_tools_pre_execute)


apply.inject = ["approvals", "tools"]  # type: ignore[attr-defined]
