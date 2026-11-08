"""Unit tests for steering-bridge plugin entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anima import Context

from mth_plugins.bridges.steering.plugin import apply


async def test_steering_plugin_apply() -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.steering.service.SteeringBridgeService.refresh_steering",
        new_callable=MagicMock,
    ) as mock_refresh:
        await apply(ctx, project_path="/proj", auto_refresh=True)
        await ctx.flush()

        assert ctx.has("steering")
        mock_refresh.assert_called_once()


async def test_steering_plugin_apply_no_auto_refresh() -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.steering.service.SteeringBridgeService.refresh_steering",
        new_callable=MagicMock,
    ) as mock_refresh:
        await apply(ctx, auto_refresh=False)
        await ctx.flush()

        assert ctx.has("steering")
        mock_refresh.assert_not_called()
