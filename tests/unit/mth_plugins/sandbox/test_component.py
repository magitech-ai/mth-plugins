"""Unit tests for sandbox component registration."""

from __future__ import annotations

from anima import Context

from mth_plugins.sandbox.component import apply
from mth_plugins.sandbox.ladder import PrivilegeLevel, SandboxService


async def test_sandbox_component_apply() -> None:
    ctx = Context()
    apply(ctx, max_level="network", enforce=True)
    await ctx.flush()

    assert ctx.has("sandbox")
    svc: SandboxService = ctx.sandbox
    assert svc.max_level == PrivilegeLevel.NETWORK
    assert svc.enforce is True
