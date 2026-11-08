"""Unit tests for directory tree hashing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mth_plugins.guards.trust.hasher import (
    EMPTY_TREE_HASH,
    compute_directory_tree_hash,
)


def test_tree_hash_non_existent_and_empty(tmp_path: Path) -> None:
    # Non-existent directory
    assert compute_directory_tree_hash(tmp_path / "not-there") == EMPTY_TREE_HASH

    # Empty directory
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert compute_directory_tree_hash(empty_dir) == EMPTY_TREE_HASH


def test_tree_hash_files_and_ignored_dirs(tmp_path: Path) -> None:
    target_dir = tmp_path / "project_agents"
    target_dir.mkdir()

    # Create file A and B
    (target_dir / "b.txt").write_text("content B")
    (target_dir / "a.txt").write_text("content A")

    # Create ignored file in __pycache__ and .git
    pycache = target_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "compiled.pyc").write_text("cache data")

    git_dir = target_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config")

    hash1 = compute_directory_tree_hash(target_dir)
    assert hash1.startswith("sha256:")
    assert hash1 != EMPTY_TREE_HASH

    # Mutate ignored file: hash should NOT change
    (pycache / "compiled.pyc").write_text("mutated cache")
    assert compute_directory_tree_hash(target_dir) == hash1

    # Mutate tracked file: hash MUST change
    (target_dir / "a.txt").write_text("content A mutated")
    hash2 = compute_directory_tree_hash(target_dir)
    assert hash2 != hash1


def test_tree_hash_os_error_handling(tmp_path: Path) -> None:
    target_dir = tmp_path / "os_err_dir"
    target_dir.mkdir()
    (target_dir / "file.txt").write_text("sample")

    with patch.object(Path, "stat", side_effect=OSError("Permission denied")):
        # Gracefully skips unreadable file and finishes
        h = compute_directory_tree_hash(target_dir)
        assert h.startswith("sha256:")
