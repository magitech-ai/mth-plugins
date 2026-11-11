"""Anima component entry point for skills-bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anima import Context

from mth_plugins.bridges.skills.service import SkillsBridgeService


async def apply(
    ctx: Context,
    skills_dir: str | Path | None = None,
    auto_discover: bool = True,
    **kwargs: Any,
) -> None:
    """Anima component registering SkillsBridgeService and discovering skills."""
    ctx.use(SkillsBridgeService)
    await ctx.flush()

    if auto_discover and ctx.has("skills"):
        service: SkillsBridgeService = ctx.skills
        service.discover_skills(explicit_dir=skills_dir)
