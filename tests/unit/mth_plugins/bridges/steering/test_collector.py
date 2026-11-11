"""Unit tests for steering document collection and formatting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from magitech_harness.components.layers import ConfigLayer

from mth_plugins.bridges.steering.collector import (
    LayerSteeringDocument,
    collect_steering_documents,
    format_hierarchical_steering,
)


def test_collect_steering_documents(tmp_path: Path) -> None:
    # 1. Global layer with AGENTS.md
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "AGENTS.md").write_text("# Global Rules\nAlways run tests.")

    # 2. User layer with CLAUDE.md (fallback)
    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "CLAUDE.md").write_text("# User Preferences\nPrefer python3.12.")

    # 3. Agent layer with empty AGENTS.md
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "AGENTS.md").write_text("   \n  ")

    # 4. Project layer with .agents.md
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".agents.md").write_text(
        "# Project Guidelines\nStrict typing required."
    )

    # 5. Layer with no steering files
    empty_layer_dir = tmp_path / "empty_layer"
    empty_layer_dir.mkdir()

    # 6. Non-existent layer
    missing_dir = tmp_path / "missing"

    layers = [
        ConfigLayer(name="global", path=global_dir, exists=True),
        ConfigLayer(name="user", path=user_dir, exists=True),
        ConfigLayer(name="agent", path=agent_dir, exists=True),
        ConfigLayer(name="project", path=project_dir, exists=True),
        ConfigLayer(name="empty", path=empty_layer_dir, exists=True),
        ConfigLayer(name="missing", path=missing_dir, exists=False),
    ]

    docs = collect_steering_documents(layers)
    assert len(docs) == 3
    assert docs[0].layer_name == "global"
    assert "Always run tests" in docs[0].content
    assert docs[1].layer_name == "user"
    assert "Prefer python3.12" in docs[1].content
    assert docs[2].layer_name == "project"
    assert "Strict typing" in docs[2].content


def test_collect_steering_documents_os_error(tmp_path: Path) -> None:
    layer_dir = tmp_path / "unreadable"
    layer_dir.mkdir()
    agents_file = layer_dir / "AGENTS.md"
    agents_file.write_text("Secret")

    with patch.object(Path, "read_text", side_effect=OSError("Read error")):
        docs = collect_steering_documents(
            [ConfigLayer(name="layer", path=layer_dir, exists=True)]
        )
        assert len(docs) == 0


def test_format_hierarchical_steering(tmp_path: Path) -> None:
    # Empty docs
    assert format_hierarchical_steering([]) == ""

    # Framed docs
    docs = [
        LayerSteeringDocument(
            layer_name="global",
            file_path=tmp_path / "AGENTS.md",
            content="Global policy.",
        ),
        LayerSteeringDocument(
            layer_name="custom",
            file_path=tmp_path / "AGENTS.md",
            content="Custom rules.",
        ),
    ]

    formatted = format_hierarchical_steering(docs)
    assert "# Steering Guidelines" in formatted
    assert "## Global Policy Guidelines" in formatted
    assert "Global policy." in formatted
    assert "## Custom Guidelines" in formatted
    assert "Custom rules." in formatted
