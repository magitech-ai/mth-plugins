"""Unit tests for snapshot bridge package exports."""

import mth_plugins.bridges.workspace_snapshot as ws_pkg


def test_init_exports() -> None:
    assert hasattr(ws_pkg, "SnapshotEngine")
    assert hasattr(ws_pkg, "SnapshotService")
    assert hasattr(ws_pkg, "apply")
    assert hasattr(ws_pkg, "scan_worktree")
