"""SnapshotService providing snapshot, diff, and restoration operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from anima import Context, Service

from mth_plugins.bridges.workspace_snapshot.git import SnapshotEngine


class SnapshotService(Service):
    """Service orchestrating shadow Git workspace snapshots and rollbacks."""

    inject: ClassVar[list[str]] = ["sessions"]

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(ctx, "snapshots")
        cfg = config or {}
        self.workspace_root = (
            cfg.get("workspace_root")
            or getattr(ctx, "workspace_dir", None)
            or Path.cwd()
        )
        self.engine = SnapshotEngine(snapshots_root=cfg.get("snapshots_root"))

    async def capture(
        self,
        leaf_id: str,
        workspace: Path | None = None,
    ) -> str:
        """Captures a snapshot of the workspace filesystem."""
        ws = workspace or self.workspace_root
        return await self.engine.capture(leaf_id, ws)

    async def diff(
        self,
        target_snapshot: str = "latest",
        workspace: Path | None = None,
    ) -> str:
        """Computes diff against a designated snapshot."""
        ws = workspace or self.workspace_root
        return await self.engine.diff(ws, target_snapshot=target_snapshot)

    async def restore(
        self,
        snapshot_id: str,
        workspace: Path | None = None,
    ) -> bool:
        """Restores working directory to the designated snapshot tree."""
        ws = workspace or self.workspace_root
        return await self.engine.restore(snapshot_id, ws)
