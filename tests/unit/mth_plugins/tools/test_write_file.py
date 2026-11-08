"""Unit tests for write_file tool plugin."""

from __future__ import annotations

from pathlib import Path

import pytest
from anima import Context
from magitech_harness.session.events import ToolCallData
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.write_file.plugin import apply
from mth_plugins.tools.write_file.write_file import handle_write_file


@pytest.mark.asyncio
async def test_handle_write_file(tmp_path: Path) -> None:
    """Verifies handle_write_file creates nested dirs and writes content."""
    # Missing path
    res = await handle_write_file({})
    assert "required" in res

    target = tmp_path / "nested" / "sub" / "output.txt"
    res = await handle_write_file({"path": str(target), "content": "Magitech rules"})
    assert "Successfully wrote" in res
    assert target.read_text(encoding="utf-8") == "Magitech rules"


@pytest.mark.asyncio
async def test_write_plugin_integration(tmp_path: Path) -> None:
    """Verifies write_file plugin mounts and executes via ToolService."""
    ctx = Context()
    ctx.plugin(ToolService)
    ctx.plugin(apply)
    await ctx.flush()

    assert ctx.tools.get("write_file") is not None

    test_file = tmp_path / "integration_write.txt"
    call_write = ToolCallData(
        call_id="c1",
        name="write_file",
        arguments={"path": str(test_file), "content": "Integration write testing"},
    )
    res_write = await ctx.tools.execute(call_write)
    assert not res_write.is_error
    assert test_file.read_text(encoding="utf-8") == "Integration write testing"
