"""Unit tests for TrustStore persistence and evaluation."""

from __future__ import annotations

from pathlib import Path

from mth_plugins.guards.trust.store import TrustDecision, TrustStore


def test_trust_store_read_invalid_and_missing(tmp_path: Path) -> None:
    store = TrustStore(tmp_path / "trust.json")
    # Missing file
    assert store._read_data() == {"projects": {}, "trusted_parents": []}

    # Corrupted file
    store.file_path.write_text("not json{")
    assert store._read_data() == {"projects": {}, "trusted_parents": []}

    # Non-dict JSON
    store.file_path.write_text("[1, 2, 3]")
    assert store._read_data() == {"projects": {}, "trusted_parents": []}


def test_trust_store_decisions_and_parent_prefix(tmp_path: Path) -> None:
    store_file = tmp_path / "approval" / "trust.json"
    store = TrustStore(store_file)

    parent_dir = tmp_path / "workspaces"
    project_1 = parent_dir / "project-one"
    project_2 = tmp_path / "isolated" / "project-two"

    # Initially unspecified
    assert store.get_decision(project_1, "sha256:111") == TrustDecision.UNSPECIFIED

    # Whitelist parent
    store.add_trusted_parent(parent_dir)
    assert store.get_decision(project_1, "sha256:111") == TrustDecision.TRUST_PARENT
    # Calling add_trusted_parent again with same path is a no-op
    store.add_trusted_parent(parent_dir)

    # Record exact trust for project_2
    store.set_decision(project_2, TrustDecision.TRUST_EXACT, tree_hash="sha256:222")
    assert store.get_decision(project_2, "sha256:222") == TrustDecision.TRUST_EXACT

    # When tree_hash changes, returns UNSPECIFIED
    assert store.get_decision(project_2, "sha256:mutated") == TrustDecision.UNSPECIFIED

    # Record decline for project_2
    store.set_decision(project_2, TrustDecision.DECLINE)
    assert store.get_decision(project_2, "sha256:222") == TrustDecision.DECLINE

    # Record unknown decision state in JSON directly
    data = store._read_data()
    data["projects"][str(project_2.resolve())]["decision"] = "unknown_state"
    store._write_data(data)
    assert store.get_decision(project_2, "sha256:222") == TrustDecision.UNSPECIFIED

    # Clear store
    store.clear()
    assert store.get_decision(project_1, "sha256:111") == TrustDecision.UNSPECIFIED
    assert store.get_decision(project_2, "sha256:222") == TrustDecision.UNSPECIFIED
