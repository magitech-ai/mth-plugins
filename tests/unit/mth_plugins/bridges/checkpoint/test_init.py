"""Unit tests for checkpoint bridge package exports."""

import mth_plugins.bridges.checkpoint as ck_pkg


def test_init_exports() -> None:
    assert hasattr(ck_pkg, "CheckpointEngine")
    assert hasattr(ck_pkg, "CheckpointService")
    assert hasattr(ck_pkg, "apply")
    assert hasattr(ck_pkg, "scan_worktree")
