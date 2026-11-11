"""Unit tests for workspace-trust-gate component apply."""

from __future__ import annotations

from pathlib import Path

from anima import Context

from mth_plugins.guards.trust.component import apply
from mth_plugins.guards.trust.gate import WorkspaceTrustGate


async def test_trust_component_apply(tmp_path: Path) -> None:
    ctx = Context()
    apply(ctx, store_path=tmp_path / "trust.json")
    await ctx.flush()

    assert ctx.has("trust")
    gate: WorkspaceTrustGate = ctx.trust
    assert gate.store.file_path == tmp_path / "trust.json"
