"""Collector and hierarchical formatter for multi-tier steering documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from magitech_harness.components.layers import ConfigLayer

STEERING_FILENAMES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", ".agents.md")

_LAYER_HEADERS: dict[str, str] = {
    "global": "## Global Policy Guidelines",
    "user": "## User Preferences & Defaults",
    "agent": "## Agent Persona & Specialization",
    "project": "## Project Guidelines & Architecture",
}


@dataclass(frozen=True)
class LayerSteeringDocument:
    """Represents a steering markdown document discovered in a specific layer."""

    layer_name: str
    file_path: Path
    content: str


def collect_steering_documents(
    layers: list[ConfigLayer],
) -> list[LayerSteeringDocument]:
    """Scans active configuration layers for steering guidelines in precedence order."""
    collected: list[LayerSteeringDocument] = []

    for layer in layers:
        if not layer.exists or not layer.path.is_dir():
            continue

        for filename in STEERING_FILENAMES:
            candidate = layer.path / filename
            if candidate.is_file():
                try:
                    text = candidate.read_text(encoding="utf-8").strip()
                    if text:
                        collected.append(
                            LayerSteeringDocument(
                                layer_name=layer.name,
                                file_path=candidate,
                                content=text,
                            )
                        )
                    # Stop after first matching candidate in this tier
                    break
                except OSError:
                    continue

    return collected


def format_hierarchical_steering(docs: list[LayerSteeringDocument]) -> str:
    """Assembles a list of layer steering documents into framed markdown."""
    if not docs:
        return ""

    sections: list[str] = ["# Steering Guidelines"]

    for doc in docs:
        header = _LAYER_HEADERS.get(
            doc.layer_name, f"## {doc.layer_name.title()} Guidelines"
        )
        sections.append(f"{header}\n\n{doc.content}")

    return "\n\n".join(sections)
