"""Canonical SHA-256 tree hashing for directory integrity verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

EMPTY_TREE_HASH: str = f"sha256:{hashlib.sha256(b'').hexdigest()}"


def compute_directory_tree_hash(dir_path: Path) -> str:
    """Computes a canonical SHA-256 digest over all files in a directory.

    Files are sorted deterministically by relative POSIX path. The digest includes
    relative path metadata, file size, and file bytes.

    Args:
        dir_path: Root directory to hash.

    Returns:
        Canonical hash string in format 'sha256:<hex>'.
    """
    if not dir_path.is_dir():
        return EMPTY_TREE_HASH

    hasher = hashlib.sha256()
    file_entries: list[tuple[str, Path]] = []

    for path in dir_path.rglob("*"):
        if not path.is_file():
            continue
        # Skip files inside ignored directories
        parts = path.relative_to(dir_path).parts
        if any(p in IGNORED_DIR_NAMES for p in parts):
            continue
        rel_posix = path.relative_to(dir_path).as_posix()
        file_entries.append((rel_posix, path))

    if not file_entries:
        return EMPTY_TREE_HASH

    # Sort deterministically by relative posix path
    file_entries.sort(key=lambda x: x[0])

    for rel_posix, file_path in file_entries:
        try:
            stat = file_path.stat()
            # Feed file header: path:size\n
            hasher.update(f"{rel_posix}:{stat.st_size}\n".encode())
            # Feed file contents in 64 KiB chunks
            with file_path.open("rb") as f:
                while chunk := f.read(64 * 1024):
                    hasher.update(chunk)
        except OSError:
            continue

    return f"sha256:{hasher.hexdigest()}"
