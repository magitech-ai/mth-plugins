"""Shadow Git repository management, alternates sharing, and snapshot capture."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from mth_plugins.bridges.workspace_snapshot.scanner import scan_worktree

logger = logging.getLogger(__name__)


class SnapshotEngine:
    """Shadow-git snapshot engine isolating turn trees using Git alternates."""

    def __init__(self, snapshots_root: Path | None = None) -> None:
        self.snapshots_root = snapshots_root or (Path.home() / ".agents" / "snapshots")
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def git_dir_for(self, workspace: Path) -> Path:
        """Derives the deterministic shadow git directory for a workspace."""
        resolved = workspace.resolve()
        digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
        return self.snapshots_root / digest

    async def _run_git(
        self,
        git_dir: Path,
        workspace: Path,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Runs a git command against the shadow git repository."""
        cmd = ["git", "--git-dir", str(git_dir), "--work-tree", str(workspace), *args]
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            env=full_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def _ensure_git_dir(self, git_dir: Path, workspace: Path) -> None:
        """Initializes bare repository with object alternates sharing if absent."""
        if git_dir.is_dir() and (git_dir / "config").is_file():
            return

        git_dir.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "init",
            "--bare",
            str(git_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        configs = [
            ("core.autocrlf", "false"),
            ("core.longpaths", "true"),
            ("core.symlinks", "true"),
            ("core.quotepath", "false"),
        ]
        for key, val in configs:
            await self._run_git(git_dir, workspace, ["config", key, val])

        # Link primary repository objects via alternates to prevent disk duplication
        ws_objects = workspace / ".git" / "objects"
        if ws_objects.is_dir():
            alternates = git_dir / "objects" / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(f"{ws_objects.resolve()}\n", encoding="utf-8")

    def load_snapshots(self, git_dir: Path) -> dict[str, str]:
        """Loads the snapshot-to-tree-sha registry."""
        snap_file = git_dir / "snapshots.json"
        if not snap_file.is_file():
            return {}
        try:
            data = json.loads(snap_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_snapshots(self, git_dir: Path, snapshots: dict[str, str]) -> None:
        """Persists the snapshot-to-tree-sha registry."""
        snap_file = git_dir / "snapshots.json"
        snap_file.write_text(json.dumps(snapshots, indent=2), encoding="utf-8")

    async def capture(self, leaf_id: str, workspace: Path) -> str:
        """Captures a Git tree snapshot of workspace bound to leaf_id."""
        git_dir = self.git_dir_for(workspace)

        file_count, byte_count, over_bound = scan_worktree(workspace, git_dir)
        if over_bound:
            logger.warning(
                "Skipping snapshot capture for %s: worktree exceeds bounds "
                "(%d files, %d bytes)",
                workspace,
                file_count,
                byte_count,
            )
            return ""

        async with self._lock:
            await self._ensure_git_dir(git_dir, workspace)
            temp_index = git_dir / f"index.{uuid4().hex}"
            try:
                env = {"GIT_INDEX_FILE": str(temp_index)}
                await self._run_git(
                    git_dir,
                    workspace,
                    ["add", "-A", "--", ":(exclude).git", ":(exclude).agents"],
                    env=env,
                )
                code, tree_sha, stderr = await self._run_git(
                    git_dir,
                    workspace,
                    ["write-tree"],
                    env=env,
                )
                tree_sha = tree_sha.strip()
                if code != 0 or not tree_sha:
                    logger.warning("write-tree failed: %s", stderr)
                    return ""

                snapshots = self.load_snapshots(git_dir)
                snapshots[leaf_id] = tree_sha
                snapshots["latest"] = tree_sha
                self.save_snapshots(git_dir, snapshots)
                return tree_sha
            finally:
                with contextlib.suppress(OSError):
                    temp_index.unlink(missing_ok=True)

    async def diff(
        self,
        workspace: Path,
        target_snapshot: str = "latest",
    ) -> str:
        """Computes unified diff between snapshot and current working directory."""
        git_dir = self.git_dir_for(workspace)
        if not git_dir.is_dir():
            return ""

        snapshots = self.load_snapshots(git_dir)
        tree_sha = snapshots.get(target_snapshot, target_snapshot)
        if not tree_sha:
            return ""

        async with self._lock:
            temp_index = git_dir / f"index.{uuid4().hex}"
            try:
                env = {"GIT_INDEX_FILE": str(temp_index)}
                await self._run_git(
                    git_dir,
                    workspace,
                    ["add", "-A", "--", ":(exclude).git", ":(exclude).agents"],
                    env=env,
                )
                code, diff_out, _ = await self._run_git(
                    git_dir,
                    workspace,
                    ["diff", "--no-ext-diff", tree_sha, "--", "."],
                    env=env,
                )
                return diff_out if code == 0 else ""
            finally:
                with contextlib.suppress(OSError):
                    temp_index.unlink(missing_ok=True)

    async def restore(
        self,
        snapshot_id: str,
        workspace: Path,
    ) -> bool:
        """Restores workspace filesystem state from recorded snapshot tree."""
        git_dir = self.git_dir_for(workspace)
        if not git_dir.is_dir():
            return False

        snapshots = self.load_snapshots(git_dir)
        tree_sha = snapshots.get(snapshot_id, snapshot_id)
        if not tree_sha:
            return False

        async with self._lock:
            temp_index = git_dir / f"index.restore.{uuid4().hex}"
            try:
                env = {"GIT_INDEX_FILE": str(temp_index)}
                code, _, err = await self._run_git(
                    git_dir,
                    workspace,
                    ["read-tree", tree_sha],
                    env=env,
                )
                if code != 0:
                    logger.warning("read-tree failed: %s", err)
                    return False

                code, _, err = await self._run_git(
                    git_dir,
                    workspace,
                    ["checkout-index", "-a", "-f"],
                    env=env,
                )
                return code == 0
            finally:
                with contextlib.suppress(OSError):
                    temp_index.unlink(missing_ok=True)
