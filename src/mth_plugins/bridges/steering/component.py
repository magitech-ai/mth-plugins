"""Anima component entry point for steering-bridge."""

from __future__ import annotations

from typing import Any

from anima import Context

from mth_plugins.bridges.steering.service import SteeringBridgeService


async def apply(
    ctx: Context,
    config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Anima component mounting SteeringBridgeService and refreshing guidelines."""
    cfg = {**(config or {}), **kwargs}
    auto_refresh = bool(cfg.get("auto_refresh", True))
    ctx.use(
        SteeringBridgeService,
        {
            "project_path": cfg.get("project_path"),
            "agent_name": cfg.get("agent_name"),
        },
    )
    await ctx.flush()

    if auto_refresh and ctx.has("steering"):
        service: SteeringBridgeService = ctx.steering
        service.refresh_steering()
