"""Unit tests for SteeringBridgeService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from anima import Context
from magitech_harness.plugins.layers import ConfigLayer
from magitech_harness.system_prompt.service import SystemPromptService

from mth_plugins.bridges.steering.service import SteeringBridgeService


async def test_steering_service_lifecycle(tmp_path: Path) -> None:
    ctx = Context()
    ctx.use(SystemPromptService)
    await ctx.flush()

    # Create dummy steering files
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "AGENTS.md").write_text("# Fleet Policies\nNo unreviewed code.")

    mock_layers = MagicMock()
    mock_layers.get_layers.return_value = [
        ConfigLayer(name="global", path=global_dir, exists=True),
    ]
    ctx._register_service("layers", mock_layers)

    fiber = ctx.use(SteeringBridgeService)
    await ctx.flush()
    service: SteeringBridgeService = ctx.steering

    formatted = service.refresh_steering(project_path="/dummy", agent_name="tester")
    assert "No unreviewed code" in formatted
    assert service.agent_name == "tester"

    rendered = await ctx.system_prompt.render()
    assert "# Steering Guidelines" in rendered
    assert "No unreviewed code" in rendered

    # Refresh again (covers self._prompt_disposer is not None branch)
    service.refresh_steering()

    # Dispose fiber should clean up prompt section
    await fiber.dispose()
    rendered_after = await ctx.system_prompt.render()
    assert "# Steering Guidelines" not in rendered_after

    # Test disposing fiber when prompt_disposer is already None
    fiber2 = ctx.use(SteeringBridgeService)
    await ctx.flush()
    await fiber2.dispose()


async def test_steering_service_no_layers_or_prompt() -> None:
    ctx = Context()
    service = SteeringBridgeService(ctx)

    # refresh without layers or system_prompt mounted
    res = service.refresh_steering()
    assert res == ""
