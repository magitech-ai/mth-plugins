"""Unit tests for CheckpointService delegation."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from anima import Context

from mth_plugins.bridges.checkpoint.service import CheckpointService


@pytest.mark.asyncio
async def test_checkpoint_service_delegation(tmp_path: Path) -> None:
    ctx = Context()
    service = CheckpointService(
        ctx,
        {
            "checkpoints_root": tmp_path / "checkpoints",
            "workspace_root": tmp_path / "ws",
        },
    )
    assert service.workspace_root == tmp_path / "ws"

    # 1. capture delegation
    with patch.object(service.engine, "capture", AsyncMock(return_value="tree123")):
        res = await service.capture("leaf-1")
        assert res == "tree123"

    # 2. diff delegation
    with patch.object(service.engine, "diff", AsyncMock(return_value="diff content")):
        diff_res = await service.diff("latest")
        assert diff_res == "diff content"

    # 3. restore delegation
    with patch.object(service.engine, "restore", AsyncMock(return_value=True)):
        restore_res = await service.restore("leaf-1")
        assert restore_res is True
