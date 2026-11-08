"""Unit tests for workspace-trust-gate plugin apply."""

from __future__ import annotations

from pathlib import Path

from anima import Context

from mth_plugins.guards.trust.gate import WorkspaceTrustGate
from mth_plugins.guards.trust.plugin import apply


async def test_trust_plugin_apply(tmp_path: Path) -> None:
    ctx = Context()
    apply(ctx, store_path=tmp_path / "trust.json")
    await ctx.flush()

    assert ctx.has("trust")
    gate: WorkspaceTrustGate = ctx.trust
    assert gate.store.file_path == tmp_path / "trust.json"
