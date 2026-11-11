"""Unit tests for skills-bridge component entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from anima import Context

from mth_plugins.bridges.skills.component import apply


async def test_skills_component_apply(tmp_path: Path) -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.skills.service.SkillsBridgeService.discover_skills",
        new_callable=MagicMock,
    ) as mock_discover:
        await apply(ctx, skills_dir=tmp_path, auto_discover=True)
        await ctx.flush()

        assert ctx.has("skills")
        mock_discover.assert_called_once_with(explicit_dir=tmp_path)


async def test_skills_component_apply_no_auto_discover() -> None:
    ctx = Context()
    with patch(
        "mth_plugins.bridges.skills.service.SkillsBridgeService.discover_skills",
        new_callable=MagicMock,
    ) as mock_discover:
        await apply(ctx, auto_discover=False)
        await ctx.flush()

        assert ctx.has("skills")
        mock_discover.assert_not_called()
