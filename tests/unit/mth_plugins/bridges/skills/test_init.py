"""Unit tests for skills bridge package exports."""

from __future__ import annotations

from mth_plugins.bridges import skills


def test_skills_exports() -> None:
    assert hasattr(skills, "SkillPackage")
    assert hasattr(skills, "SkillsBridgeService")
    assert hasattr(skills, "parse_skill_file")
