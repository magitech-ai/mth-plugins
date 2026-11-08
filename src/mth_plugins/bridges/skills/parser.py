"""Parser for agentskills.io SKILL.md specification files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillPackage:
    """Represents a discovered and parsed Agent Skill package."""

    name: str
    description: str
    path: Path
    skill_file: Path
    body: str
    compatibility: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_frontmatter_yaml(yaml_text: str) -> dict[str, Any]:
    """Lightweight zero-dependency YAML frontmatter parser."""
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in yaml_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # List item continuation: - item
        if line.startswith("- ") and current_list_key is not None:
            val = line[2:].strip().strip("\"'")
            data[current_list_key].append(val)
            continue

        if ":" not in line:
            current_list_key = None
            continue

        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()

        if not val:
            # Key with nested list following
            current_list_key = key
            data[key] = []
        elif val.startswith("[") and val.endswith("]"):
            # Inline list: [a, b, c]
            items = [
                item.strip().strip("\"'")
                for item in val[1:-1].split(",")
                if item.strip()
            ]
            data[key] = items
            current_list_key = None
        else:
            # Scalar value
            current_list_key = None
            clean_val = val.strip("\"'")
            if clean_val.lower() == "true":
                data[key] = True
            elif clean_val.lower() == "false":
                data[key] = False
            else:
                try:
                    data[key] = int(clean_val)
                except ValueError:
                    data[key] = clean_val

    return data


def parse_skill_file(file_path: Path) -> SkillPackage:
    """Parses a SKILL.md file adhering to the agentskills.io standard.

    Args:
        file_path: Absolute or relative path to SKILL.md.

    Returns:
        Structured SkillPackage instance.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If frontmatter is missing or invalid.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Skill file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    parts = content.split("---", 2)

    if len(parts) < 3 or parts[0].strip() != "":
        raise ValueError(
            f"Invalid SKILL.md at {file_path}: "
            "Missing '---' YAML frontmatter delimiters."
        )

    frontmatter_raw = parts[1]
    body = parts[2].strip()

    frontmatter = _parse_frontmatter_yaml(frontmatter_raw)
    name = str(frontmatter.get("name", "")).strip()
    desc = str(frontmatter.get("description", "")).strip()

    if not name:
        raise ValueError(
            f"Skill at {file_path} is missing required 'name' in frontmatter."
        )
    if not desc:
        raise ValueError(
            f"Skill at {file_path} is missing required 'description' in frontmatter."
        )

    # Validate name format: lowercase alphanumeric with hyphens/underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise ValueError(
            f"Invalid skill name '{name}'. "
            "Must be alphanumeric with hyphens/underscores."
        )

    compatibility = frontmatter.get("compatibility")
    if compatibility is not None:
        compatibility = str(compatibility)

    meta = {
        k: v
        for k, v in frontmatter.items()
        if k not in ("name", "description", "compatibility")
    }

    return SkillPackage(
        name=name,
        description=desc,
        path=file_path.parent,
        skill_file=file_path,
        body=body,
        compatibility=compatibility,
        metadata=meta,
    )
