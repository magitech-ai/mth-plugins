"""Unit tests for steering bridge exports."""

from __future__ import annotations

from mth_plugins.bridges import steering


def test_steering_exports() -> None:
    assert hasattr(steering, "LayerSteeringDocument")
    assert hasattr(steering, "SteeringBridgeService")
    assert hasattr(steering, "collect_steering_documents")
    assert hasattr(steering, "format_hierarchical_steering")
