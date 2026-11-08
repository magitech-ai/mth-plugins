"""CheckpointService providing snapshot, diff, and restoration operations."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from anima import Context, Service

from mth_plugins.bridges.checkpoint.git import CheckpointEngine


class CheckpointService(Service):
    """Service orchestrating shadow Git workspace snapshots and rollbacks."""

    inject: ClassVar[list[str]] = ["sessions"]

    def __init__(
        self,
        ctx: Context,
        checkpoints_root: Path | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        super().__init__(ctx, "checkpoints")
        self.workspace_root = (
            workspace_root or getattr(ctx, "workspace_dir", None) or Path.cwd()
        )
        self.engine = CheckpointEngine(checkpoints_root=checkpoints_root)

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
        target_checkpoint: str = "latest",
        workspace: Path | None = None,
    ) -> str:
        """Computes diff against a designated checkpoint snapshot."""
        ws = workspace or self.workspace_root
        return await self.engine.diff(ws, target_checkpoint=target_checkpoint)

    async def restore(
        self,
        checkpoint_id: str,
        workspace: Path | None = None,
    ) -> bool:
        """Restores working directory to the designated snapshot tree."""
        ws = workspace or self.workspace_root
        return await self.engine.restore(checkpoint_id, ws)
