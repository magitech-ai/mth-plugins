"""Unit tests for workspace-trust-gate exports."""

from __future__ import annotations

from mth_plugins.guards import trust


def test_trust_exports() -> None:
    assert hasattr(trust, "TrustDecision")
    assert hasattr(trust, "TrustStore")
    assert hasattr(trust, "WorkspaceTrustGate")
    assert hasattr(trust, "compute_directory_tree_hash")
