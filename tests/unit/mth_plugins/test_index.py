"""Unit tests for marketplace catalog indexing and resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from magitech_harness.plugins.manifest import PluginManifest

from mth_plugins.index import (
    REPO_ROOT,
    ComponentArtifact,
    _determine_kind,
    build_catalog,
    find_component,
    load_index,
    scan_components,
)


def test_component_artifact_properties(tmp_path: Path) -> None:
    """Verifies relative_path and entry_point_path resolution."""
    manifest = PluginManifest(
        name="test-component",
        version="1.0.0",
        entry_point="component.py:apply",
    )
    component_dir = tmp_path / "test_component"
    art = ComponentArtifact(
        name="test-component",
        kind="tool",
        path=component_dir,
        manifest=manifest,
    )

    # Outside REPO_ROOT: falls back to as_posix()
    assert art.relative_path == component_dir.as_posix()
    assert art.entry_point_path == component_dir / "component.py"

    # Inside REPO_ROOT
    inside_dir = REPO_ROOT / "src" / "mth_plugins" / "tools" / "bash"
    art_inside = ComponentArtifact(
        name="bash-tool",
        kind="tool",
        path=inside_dir,
        manifest=manifest,
    )
    assert art_inside.relative_path == "src/mth_plugins/tools/bash"


def test_determine_kind(tmp_path: Path) -> None:
    """Verifies kind detection logic across all branches."""
    # 1. "providers" in parts
    m1 = PluginManifest(name="p1", version="1.0", entry_point="p.py")
    assert _determine_kind(tmp_path / "providers" / "p1", m1) == "provider"

    # 2. "Provider" in types
    m2 = PluginManifest(
        name="p2", version="1.0", entry_point="p.py", types=["Provider"]
    )
    assert _determine_kind(tmp_path / "custom" / "p2", m2) == "provider"

    # 3. "guards" in parts
    assert _determine_kind(tmp_path / "guards" / "g1", m1) == "guard"

    # 4. "Guard" in types
    m3 = PluginManifest(name="g2", version="1.0", entry_point="p.py", types=["Guard"])
    assert _determine_kind(tmp_path / "custom" / "g2", m3) == "guard"

    # 5. "tools" in parts
    assert _determine_kind(tmp_path / "tools" / "t1", m1) == "tool"

    # 6. "Tool" in types
    m4 = PluginManifest(name="t2", version="1.0", entry_point="p.py", types=["Tool"])
    assert _determine_kind(tmp_path / "custom" / "t2", m4) == "tool"

    # 7. "bridges" in parts and "Bridge" in types
    assert _determine_kind(tmp_path / "bridges" / "b1", m1) == "bridge"
    m5 = PluginManifest(name="b2", version="1.0", entry_point="p.py", types=["Bridge"])
    assert _determine_kind(tmp_path / "custom" / "b2", m5) == "bridge"

    # 8. "sandbox" in parts and "Sandbox" in types
    assert _determine_kind(tmp_path / "sandbox" / "s1", m1) == "sandbox"
    m6 = PluginManifest(name="s2", version="1.0", entry_point="p.py", types=["Sandbox"])
    assert _determine_kind(tmp_path / "custom" / "s2", m6) == "sandbox"

    # 9. "sessions" in parts and "Session" in types
    assert _determine_kind(tmp_path / "sessions" / "sess1", m1) == "session"
    m_sess = PluginManifest(
        name="sess2", version="1.0", entry_point="p.py", types=["Session"]
    )
    assert _determine_kind(tmp_path / "custom" / "sess2", m_sess) == "session"

    # 10. Other custom type
    m7 = PluginManifest(name="c1", version="1.0", entry_point="p.py", types=["Custom"])
    assert _determine_kind(tmp_path / "other" / "c1", m7) == "custom"

    # 11. No type, not in special directory
    assert _determine_kind(tmp_path / "custom" / "x1", m1) == "extension"


def test_load_index(tmp_path: Path) -> None:
    """Verifies load_index parses valid catalog and raises on missing file."""
    data = load_index()
    assert "providers" in data
    assert "tools" in data
    assert "sessions" in data

    custom_index = tmp_path / "custom.json"
    custom_index.write_text(json.dumps({"test": 123}), encoding="utf-8")
    assert load_index(custom_index) == {"test": 123}

    with pytest.raises(FileNotFoundError, match="Marketplace index not found"):
        load_index(tmp_path / "nonexistent.json")


def test_scan_and_find_components(tmp_path: Path) -> None:
    """Verifies scanning components, filtering out invalid or ignored directories."""
    # Provider
    prov_dir = tmp_path / "providers" / "my_prov"
    prov_dir.mkdir(parents=True)
    (prov_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "my-prov",
                "version": "0.1.0",
                "entry_point": "component.py:apply",
                "types": ["Provider"],
            }
        ),
        encoding="utf-8",
    )

    # Bridge (standard bridge section in catalog)
    bridge_dir = tmp_path / "custom" / "my_bridge"
    bridge_dir.mkdir(parents=True)
    (bridge_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "my-bridge",
                "version": "0.1.0",
                "entry_point": "component.py",
                "types": ["Bridge"],
            }
        ),
        encoding="utf-8",
    )

    # Extension (creates non-standard 'extensions' section in catalog)
    ext_dir = tmp_path / "custom" / "my_ext"
    ext_dir.mkdir(parents=True)
    (ext_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "my-ext",
                "version": "0.1.0",
                "entry_point": "component.py",
                "types": ["Extension"],
            }
        ),
        encoding="utf-8",
    )

    # Ignored directory (.venv)
    ignored_dir = tmp_path / ".venv" / "bad"
    ignored_dir.mkdir(parents=True)
    (ignored_dir / "manifest.json").write_text("{}", encoding="utf-8")

    # Malformed manifest
    bad_dir = tmp_path / "bad_manifest"
    bad_dir.mkdir()
    (bad_dir / "manifest.json").write_text("{malformed", encoding="utf-8")

    artifacts = scan_components(tmp_path)
    names = {a.name for a in artifacts}
    assert "my-prov" in names
    assert "my-bridge" in names
    assert "my-ext" in names
    assert len(artifacts) == 3

    found = find_component("my-prov", root=tmp_path)
    assert found is not None
    assert found.kind == "provider"

    assert find_component("nonexistent", root=tmp_path) is None

    catalog = build_catalog(tmp_path)
    assert "my-prov" in catalog["providers"]
    assert "my-bridge" in catalog["bridges"]
    assert "my-ext" in catalog["extensions"]


def test_index_json_matches_scanned_catalog() -> None:
    """index.json must equal the catalog derived from manifests."""
    assert load_index() == build_catalog()
