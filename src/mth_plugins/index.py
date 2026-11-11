"""Marketplace catalog index, validation, and discovery.

Provides indexing and resolution of portable Magitech components and profiles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from magitech_harness.plugins.manifest import PluginManifest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INDEX_PATH = REPO_ROOT / "index.json"


@dataclass(frozen=True)
class ComponentArtifact:
    """Represents a discovered marketplace component artifact."""

    name: str
    kind: str
    path: Path
    manifest: PluginManifest

    @property
    def relative_path(self) -> str:
        """Returns relative path from marketplace root."""
        try:
            return self.path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    @property
    def entry_point_path(self) -> Path:
        """Resolves entry point file path relative to component directory."""
        entry = self.manifest.entry_point.split(":", 1)[0]
        return self.path / entry


def load_index(index_path: Path | None = None) -> dict[str, Any]:
    """Loads and parses the marketplace index.json catalog.

    Args:
        index_path: Optional explicit path to index.json.

    Returns:
        Parsed catalog dictionary.

    Raises:
        FileNotFoundError: If index file does not exist.
    """
    path = index_path or DEFAULT_INDEX_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Marketplace index not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


_KIND_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("providers", "provider"),
    ("guards", "guard"),
    ("bridges", "bridge"),
    ("tools", "tool"),
    ("sandbox", "sandbox"),
    ("sessions", "session"),
)


def _determine_kind(component_dir: Path, manifest: PluginManifest) -> str:
    parts = set(component_dir.parts)
    for folder, kind in _KIND_MAPPINGS:
        if folder in parts:
            return kind
    for _, kind in _KIND_MAPPINGS:
        if kind.capitalize() in manifest.types:
            return kind
    if manifest.types:
        return manifest.types[0].lower()
    return "extension"


def scan_components(root: Path | None = None) -> list[ComponentArtifact]:
    """Scans the repository for all directories containing manifest.json.

    Args:
        root: Root directory to search from. Defaults to REPO_ROOT.

    Returns:
        List of successfully parsed ComponentArtifact instances.
    """
    search_root = root or REPO_ROOT
    artifacts: list[ComponentArtifact] = []

    for manifest_path in sorted(search_root.glob("**/manifest.json")):
        # Skip manifests in virtual environments, caches, or build dirs
        parts = manifest_path.parts
        ignored_prefixes = (".",)
        ignored_names = ("venv", ".venv", "dist", "build")
        if any(p.startswith(ignored_prefixes) or p in ignored_names for p in parts):
            continue

        try:
            content = manifest_path.read_text(encoding="utf-8")
            data = json.loads(content)
            data["path"] = manifest_path.parent
            manifest = PluginManifest.model_validate(data)

            component_dir = manifest_path.parent
            kind = _determine_kind(component_dir, manifest)

            artifacts.append(
                ComponentArtifact(
                    name=manifest.name,
                    kind=kind,
                    path=component_dir,
                    manifest=manifest,
                )
            )
        except Exception:
            continue

    return artifacts


def build_catalog(root: Path | None = None) -> dict[str, Any]:
    """Builds an index catalog dictionary from all scanned components.

    Args:
        root: Root directory to scan.

    Returns:
        Structured catalog with 'providers' and 'tools' sections.
    """
    artifacts = scan_components(root)
    catalog: dict[str, Any] = {
        "providers": {},
        "tools": {},
        "guards": {},
        "bridges": {},
        "sandboxes": {},
    }

    for art in artifacts:
        target_section = "sandboxes" if art.kind == "sandbox" else f"{art.kind}s"
        if target_section not in catalog:
            catalog[target_section] = {}
        catalog[target_section][art.name] = {
            "version": art.manifest.version,
            "description": art.manifest.description,
            "path": art.relative_path,
            "entry_point": art.manifest.entry_point,
            "types": art.manifest.types,
            "enabled": art.manifest.enabled,
        }

    return catalog


def find_component(name: str, root: Path | None = None) -> ComponentArtifact | None:
    """Finds a component artifact by unique name.

    Args:
        name: Name of the component.
        root: Root directory to search from.

    Returns:
        ComponentArtifact if found, None otherwise.
    """
    for artifact in scan_components(root):
        if artifact.name == name:
            return artifact
    return None
