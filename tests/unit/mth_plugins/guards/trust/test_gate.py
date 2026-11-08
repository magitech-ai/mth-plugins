"""Unit tests for WorkspaceTrustGate verification flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from anima import Context
from magitech_harness.approval.service import ApprovalService

from mth_plugins.guards.trust.gate import WorkspaceTrustGate
from mth_plugins.guards.trust.store import TrustDecision, TrustStore


async def test_gate_project_no_agents_dir(tmp_path: Path) -> None:
    ctx = Context()
    gate = WorkspaceTrustGate(ctx, store_path=tmp_path / "trust.json")
    # Empty project without .agents is safe
    assert await gate.check_project_trust(tmp_path / "plain_project") is True


async def test_gate_project_cached_decisions(tmp_path: Path) -> None:
    ctx = Context()
    store = TrustStore(tmp_path / "trust.json")
    gate = WorkspaceTrustGate(ctx, store=store)

    project_dir = tmp_path / "my_project"
    agents_dir = project_dir / ".agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "plugin.json").write_text("{}")

    # 1. Unspecified, prompt_user=False -> returns False
    assert await gate.check_project_trust(project_dir, prompt_user=False) is False

    # 2. Record decline -> returns False
    store.set_decision(project_dir, TrustDecision.DECLINE)
    assert await gate.check_project_trust(project_dir) is False

    # 3. Whitelist parent -> returns True
    store.add_trusted_parent(tmp_path)
    assert await gate.check_project_trust(project_dir) is True


async def test_gate_prompt_user_approval_flow(tmp_path: Path) -> None:
    ctx = Context()
    mock_approvals = AsyncMock(spec=ApprovalService)
    ctx._register_service("approvals", mock_approvals)

    store = TrustStore(tmp_path / "trust.json")
    gate = WorkspaceTrustGate(ctx, store=store)

    project_dir = tmp_path / "promptee"
    agents_dir = project_dir / ".agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "tool.py").write_text("# code")

    # 1. User approves
    mock_approvals.request_approval.return_value = True
    assert await gate.check_project_trust(project_dir, prompt_user=True) is True
    mock_approvals.request_approval.assert_awaited_once()

    # Now exact trust is cached
    mock_approvals.request_approval.reset_mock()
    assert await gate.check_project_trust(project_dir) is True
    mock_approvals.request_approval.assert_not_awaited()

    # 2. User declines next project
    proj_2 = tmp_path / "declined_project"
    (proj_2 / ".agents").mkdir(parents=True)
    (proj_2 / ".agents" / "x.py").write_text("x")

    mock_approvals.request_approval.return_value = False
    assert await gate.check_project_trust(proj_2, prompt_user=True) is False
