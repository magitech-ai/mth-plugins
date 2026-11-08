"""Unit tests for SKILL.md parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from mth_plugins.bridges.skills.parser import (
    SkillPackage,
    _parse_frontmatter_yaml,
    parse_skill_file,
)


def test_parse_frontmatter_yaml_features() -> None:
    yaml_text = """
    # Comment line
    name: "data-analyzer"
    description: 'Process datasets'
    version: 2
    enabled: true
    disabled: false
    tags: [csv, json, parquet]
    tools:
      - bash
      - read_file
    # Malformed line without colon
    invalid line
    """
    data = _parse_frontmatter_yaml(yaml_text)
    assert data["name"] == "data-analyzer"
    assert data["description"] == "Process datasets"
    assert data["version"] == 2
    assert data["enabled"] is True
    assert data["disabled"] is False
    assert data["tags"] == ["csv", "json", "parquet"]
    assert data["tools"] == ["bash", "read_file"]


def test_parse_skill_file_success(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "web-scraper"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"

    content = """---
name: web-scraper
description: Scrapes HTML pages and returns text.
compatibility: python
author: dev
---
# Web Scraper Instructions
Execute scraper script to fetch URLs.
"""
    skill_file.write_text(content, encoding="utf-8")

    pkg = parse_skill_file(skill_file)
    assert isinstance(pkg, SkillPackage)
    assert pkg.name == "web-scraper"
    assert pkg.description == "Scrapes HTML pages and returns text."
    assert pkg.compatibility == "python"
    assert pkg.metadata == {"author": "dev"}
    assert "Execute scraper script" in pkg.body
    assert pkg.path == skill_dir
    assert pkg.skill_file == skill_file


def test_parse_skill_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_skill_file(tmp_path / "non-existent" / "SKILL.md")


def test_parse_skill_file_missing_delimiters(tmp_path: Path) -> None:
    bad_file = tmp_path / "SKILL.md"
    bad_file.write_text("No frontmatter here\nJust text")
    with pytest.raises(ValueError, match="Missing '---' YAML frontmatter delimiters"):
        parse_skill_file(bad_file)


def test_parse_skill_file_missing_name(tmp_path: Path) -> None:
    bad_file = tmp_path / "SKILL.md"
    bad_file.write_text("---\ndescription: Has no name\n---\nBody")
    with pytest.raises(ValueError, match="missing required 'name'"):
        parse_skill_file(bad_file)


def test_parse_skill_file_missing_description(tmp_path: Path) -> None:
    bad_file = tmp_path / "SKILL.md"
    bad_file.write_text("---\nname: my-skill\n---\nBody")
    with pytest.raises(ValueError, match="missing required 'description'"):
        parse_skill_file(bad_file)


def test_parse_skill_file_invalid_name(tmp_path: Path) -> None:
    bad_file = tmp_path / "SKILL.md"
    bad_file.write_text("---\nname: bad name with spaces\ndescription: test\n---\nBody")
    with pytest.raises(ValueError, match="Invalid skill name"):
        parse_skill_file(bad_file)
