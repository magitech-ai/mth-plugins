"""Unit tests for read_file tool plugin."""

from __future__ import annotations

from pathlib import Path

import pytest
from anima import Context
from magitech_harness.session.events import ToolCallData
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.read_file.plugin import apply
from mth_plugins.tools.read_file.read_file import handle_read_file


@pytest.mark.asyncio
async def test_handle_read_file_validation(tmp_path: Path) -> None:
    """Verifies argument validation and error cases for handle_read_file."""
    # Missing path
    res = await handle_read_file({})
    assert "required" in res

    # Invalid offset
    res = await handle_read_file({"path": "foo.txt", "offset": 0})
    assert "Invalid offset" in res

    # Invalid limit
    res = await handle_read_file({"path": "foo.txt", "limit": 0})
    assert "Invalid limit" in res

    # Nonexistent file
    res = await handle_read_file({"path": str(tmp_path / "nonexistent.txt")})
    assert "File not found" in res

    # Directory without SKILL.md
    dir_path = tmp_path / "empty_dir"
    dir_path.mkdir()
    res = await handle_read_file({"path": str(dir_path)})
    assert "Cannot read directory" in res


@pytest.mark.asyncio
async def test_handle_read_file_skill_dir_and_binary(tmp_path: Path) -> None:
    """Verifies reading skill directory with SKILL.md and binary detection."""
    # Directory with SKILL.md
    dir_path = tmp_path / "skill_dir"
    dir_path.mkdir()
    (dir_path / "SKILL.md").write_text("Skill Content", encoding="utf-8")
    res = await handle_read_file({"path": str(dir_path)})
    assert res == "Skill Content"

    # Binary file with null bytes
    bin_file = tmp_path / "binary.bin"
    bin_file.write_bytes(b"hello\x00world")
    res = await handle_read_file({"path": str(bin_file)})
    assert "Binary file not supported" in res

    # Binary file with invalid UTF-8
    bad_utf8 = tmp_path / "bad.txt"
    bad_utf8.write_bytes(b"\xff\xfe\xfd")
    res = await handle_read_file({"path": str(bad_utf8)})
    assert "Binary file not supported" in res


@pytest.mark.asyncio
async def test_handle_read_file_pagination(tmp_path: Path) -> None:
    """Verifies pagination offsets and limits for handle_read_file."""
    text_file = tmp_path / "sample.txt"
    text_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")

    # Read full file
    res = await handle_read_file({"path": str(text_file)})
    assert res == "line1\nline2\nline3\nline4"

    # Read with offset
    res = await handle_read_file({"path": str(text_file), "offset": 2})
    assert res == "line2\nline3\nline4"

    # Read with offset and limit
    res = await handle_read_file({"path": str(text_file), "offset": 2, "limit": 2})
    assert res == "line2\nline3"

    # Offset beyond EOF
    res = await handle_read_file({"path": str(text_file), "offset": 10})
    assert "beyond end of file" in res


@pytest.mark.asyncio
async def test_read_plugin_integration(tmp_path: Path) -> None:
    """Verifies read_file plugin mounts and executes via ToolService."""
    ctx = Context()
    ctx.plugin(ToolService)
    ctx.plugin(apply)
    await ctx.flush()

    assert ctx.tools.get("read_file") is not None

    test_file = tmp_path / "integration_read.txt"
    test_file.write_text("Read me successfully", encoding="utf-8")

    call_read = ToolCallData(
        call_id="c1",
        name="read_file",
        arguments={"path": str(test_file)},
    )
    res_read = await ctx.tools.execute(call_read)
    assert not res_read.is_error
    assert res_read.content == "Read me successfully"
