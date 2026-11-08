"""Anima plugin entry point for steering-bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anima import Context

from mth_plugins.bridges.steering.service import SteeringBridgeService


async def apply(
    ctx: Context,
    project_path: Path | str | None = None,
    agent_name: str | None = None,
    auto_refresh: bool = True,
    **kwargs: Any,
) -> None:
    """Anima plugin mounting SteeringBridgeService and refreshing prompt guidelines."""
    ctx.plugin(
        SteeringBridgeService,
        project_path=project_path,
        agent_name=agent_name,
    )
    await ctx.flush()

    if auto_refresh and ctx.has("steering"):
        service: SteeringBridgeService = ctx.steering
        service.refresh_steering()
