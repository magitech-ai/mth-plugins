"""Skills bridge package for Magitech Harness adhering to agentskills.io."""

from __future__ import annotations

from mth_plugins.bridges.skills.parser import SkillPackage, parse_skill_file
from mth_plugins.bridges.skills.service import SkillsBridgeService

__all__ = [
    "SkillPackage",
    "SkillsBridgeService",
    "parse_skill_file",
]
