"""Unit tests for SnapshotEngine Git operations and snapshot lifecycle."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mth_plugins.bridges.workspace_snapshot.git import SnapshotEngine


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".git" / "objects").mkdir(parents=True)
    (ws / "file.txt").write_text("initial version", encoding="utf-8")
    return ws


def test_git_dir_and_snapshots_storage(tmp_path: Path, workspace: Path) -> None:
    engine = SnapshotEngine(snapshots_root=tmp_path / "snapshots")
    git_dir = engine.git_dir_for(workspace)
    assert len(git_dir.name) == 16

    # Missing snapshots file
    assert engine.load_snapshots(git_dir) == {}

    # Save and reload
    git_dir.mkdir(parents=True)
    engine.save_snapshots(git_dir, {"t1": "sha123", "latest": "sha123"})
    loaded = engine.load_snapshots(git_dir)
    assert loaded["t1"] == "sha123"

    # Corrupted snapshots file
    (git_dir / "snapshots.json").write_text("not json", encoding="utf-8")
    assert engine.load_snapshots(git_dir) == {}

    # Non-dict JSON in snapshots file
    (git_dir / "snapshots.json").write_text("[]", encoding="utf-8")
    assert engine.load_snapshots(git_dir) == {}


@pytest.mark.asyncio
async def test_ensure_git_dir(tmp_path: Path, workspace: Path) -> None:
    engine = SnapshotEngine(snapshots_root=tmp_path / "snapshots")
    git_dir = engine.git_dir_for(workspace)

    # 1. Initialize bare git repository with alternates
    await engine._ensure_git_dir(git_dir, workspace)
    assert git_dir.is_dir()
    alternates_file = git_dir / "objects" / "info" / "alternates"
    assert alternates_file.is_file()
    assert str(workspace / ".git" / "objects") in alternates_file.read_text(
        encoding="utf-8"
    )

    # 2. Re-invoking when already initialized is a no-op
    await engine._ensure_git_dir(git_dir, workspace)


@pytest.mark.asyncio
async def test_snapshot_capture_diff_and_restore(
    tmp_path: Path, workspace: Path
) -> None:
    engine = SnapshotEngine(snapshots_root=tmp_path / "snapshots")

    # 1. Capture snapshot when worktree exceeds bounds
    with patch(
        "mth_plugins.bridges.workspace_snapshot.git.scan_worktree",
        return_value=(1000, 1000, True),
    ):
        assert await engine.capture("turn-0", workspace) == ""

    # 2. Successful capture
    tree_sha = await engine.capture("turn-1", workspace)
    assert tree_sha != ""

    # Check snapshots.json recorded the tree_sha
    git_dir = engine.git_dir_for(workspace)
    snapshots = engine.load_snapshots(git_dir)
    assert snapshots["turn-1"] == tree_sha
    assert snapshots["latest"] == tree_sha

    # 3. Diff without modifications -> empty diff
    diff_empty = await engine.diff(workspace, target_snapshot="turn-1")
    assert diff_empty == ""

    # Modify file and diff
    (workspace / "file.txt").write_text("modified text", encoding="utf-8")
    diff_out = await engine.diff(workspace, target_snapshot="turn-1")
    assert "-initial version" in diff_out
    assert "+modified text" in diff_out

    # 4. Restore workspace from snapshot
    success = await engine.restore("turn-1", workspace)
    assert success is True
    assert (workspace / "file.txt").read_text(encoding="utf-8") == "initial version"


@pytest.mark.asyncio
async def test_snapshot_edge_cases_and_failures(tmp_path: Path) -> None:
    engine = SnapshotEngine(snapshots_root=tmp_path / "snapshots")
    fake_ws = tmp_path / "fake"
    fake_ws.mkdir()

    # 1. Diff on non-existent git dir returns ""
    assert await engine.diff(fake_ws) == ""

    # 2. Restore on non-existent git dir returns False
    assert await engine.restore("latest", fake_ws) is False

    # 3. Target snapshot missing in existing git dir
    git_dir = engine.git_dir_for(fake_ws)
    git_dir.mkdir(parents=True)
    assert await engine.diff(fake_ws, target_snapshot="nonexistent") == ""
    assert await engine.diff(fake_ws, target_snapshot="") == ""
    assert await engine.restore("nonexistent", fake_ws) is False
    assert await engine.restore("", fake_ws) is False

    # 4. write-tree failure during capture
    with patch.object(
        engine, "_run_git", AsyncMock(return_value=(1, "", "fatal error"))
    ):
        res = await engine.capture("turn-fail", fake_ws)
        assert res == ""

    # 5. read-tree failure during restore
    engine.save_snapshots(git_dir, {"bad_tree": "deadbeef"})
    with patch.object(
        engine, "_run_git", AsyncMock(return_value=(1, "", "fatal tree missing"))
    ):
        assert await engine.restore("bad_tree", fake_ws) is False

    # 6. git diff execution failure in diff
    with patch.object(
        engine,
        "_run_git",
        AsyncMock(side_effect=[(0, "", ""), (1, "", "diff failure")]),
    ):
        assert await engine.diff(fake_ws, target_snapshot="bad_tree") == ""
