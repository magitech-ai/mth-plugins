"""Fail-closed layered approval guard for tool execution authorization."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from anima import Context
from magitech_harness.approval.service import ApprovalRequest
from magitech_harness.tools.service import ToolCallData

from mth_plugins.guards.approval.policy import ApprovalPolicy
from mth_plugins.guards.approval.types import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalPresenter,
    ApprovalScope,
    PolicyRule,
)

logger = logging.getLogger(__name__)

SAFE_READ_TOOLS = frozenset(
    {
        "read_file",
        "list_files",
        "find",
        "grep",
        "read_url",
        "lsp_definition",
        "lsp_references",
    }
)


class ApprovalGuard:
    """Evaluates multi-tier policies and delegates to interactive presenters."""

    def __init__(
        self,
        ctx: Context,
        workspace_policy_path: Path | None = None,
        global_policy_path: Path | None = None,
        presenter: ApprovalPresenter | None = None,
        require_all_mutations: bool = True,
    ) -> None:
        self.ctx = ctx
        self.workspace_policy_path = workspace_policy_path
        self.global_policy_path = global_policy_path
        self.presenter = presenter
        self.require_all_mutations = require_all_mutations
        self._session_grants: dict[str, bool] = {}

        self.workspace_policy = (
            ApprovalPolicy.load(workspace_policy_path)
            if workspace_policy_path
            else ApprovalPolicy([])
        )
        self.global_policy = (
            ApprovalPolicy.load(global_policy_path)
            if global_policy_path
            else ApprovalPolicy([])
        )

    def set_presenter(self, presenter: ApprovalPresenter | None) -> None:
        """Sets the interactive UI presenter callback."""
        self.presenter = presenter

    async def evaluate_request(self, request: ApprovalRequest) -> bool:
        """Evaluates an ApprovalRequest against layered policies and presenter."""
        # Check in-memory session grants by tool or digest
        if request.digest in self._session_grants:
            return self._session_grants[request.digest]

        # 1. Project / Workspace policy (highest precedence)
        decision = self.workspace_policy.evaluate(request)

        # 2. Global policy fallback
        if decision is None:
            decision = self.global_policy.evaluate(request)

        if decision is not None:
            return decision.outcome is ApprovalOutcome.ALLOW

        # 3. Interactive UI presenter
        if self.presenter is not None:
            try:
                user_decision = await self.presenter(request)
            except Exception:
                logger.exception(
                    "Approval presenter raised exception; denying fail-closed"
                )
                return False

            if (
                not isinstance(user_decision, ApprovalDecision)
                or user_decision.request_digest != request.digest
            ):
                logger.warning(
                    "Invalid or stale approval decision; denying fail-closed"
                )
                return False

            if user_decision.outcome is ApprovalOutcome.ALLOW:
                if user_decision.scope in (
                    ApprovalScope.SESSION,
                    ApprovalScope.PROJECT,
                ):
                    self._session_grants[request.digest] = True
                    approvals_svc = getattr(self.ctx, "approvals", None)
                    if approvals_svc is not None and hasattr(approvals_svc, "remember"):
                        approvals_svc.remember(request.digest, True)

                if (
                    user_decision.scope is ApprovalScope.PROJECT
                    and self.workspace_policy_path is not None
                ):
                    rule = PolicyRule(
                        tool_pattern=request.tool_name,
                        outcome=ApprovalOutcome.ALLOW,
                    )
                    self.workspace_policy.save_rule(self.workspace_policy_path, rule)

                return True

            return False

        # Fail-closed if no policy matches and no presenter is available
        return False

    async def handle_tool_pre_execute(
        self,
        tool_call: ToolCallData,
        next_fn: Callable[[ToolCallData], Awaitable[Any]],
    ) -> Any:
        """Pre-execute waterfall hook enforcing authorization before tool execution."""
        # If safe read tool, bypass approval if configured
        if self.require_all_mutations and tool_call.name in SAFE_READ_TOOLS:
            return await next_fn(tool_call)

        approvals_svc = getattr(self.ctx, "approvals", None)
        if approvals_svc is not None and hasattr(approvals_svc, "request_approval"):
            verdict = await approvals_svc.request_approval(
                tool_call.name,
                tool_call.arguments,
                description=f"Invocation of tool '{tool_call.name}'",
            )
            if not verdict:
                raise PermissionError(f"Approval denied for tool '{tool_call.name}'.")

        return await next_fn(tool_call)
