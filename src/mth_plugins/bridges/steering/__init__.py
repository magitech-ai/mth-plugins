"""Steering bridge package for Magitech Harness resolving AGENTS.md guidelines."""

from __future__ import annotations

from mth_plugins.bridges.steering.collector import (
    LayerSteeringDocument,
    collect_steering_documents,
    format_hierarchical_steering,
)
from mth_plugins.bridges.steering.service import SteeringBridgeService

__all__ = [
    "LayerSteeringDocument",
    "SteeringBridgeService",
    "collect_steering_documents",
    "format_hierarchical_steering",
]
