"""Unit tests for bash tool and plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from anima import Context
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.bash.bash import handle_bash
from mth_plugins.tools.bash.plugin import apply


@pytest.mark.asyncio
async def test_handle_bash_validation(tmp_path: Path) -> None:
    """Verifies argument validation for handle_bash."""
    # Missing command
    res = await handle_bash({})
    assert "required" in res

    # Nonexistent working directory
    res_bad_cwd = await handle_bash(
        {
            "command": "ls",
            "cwd": str(tmp_path / "nonexistent_directory"),
        }
    )
    assert "Working directory does not exist" in res_bad_cwd


@pytest.mark.asyncio
async def test_handle_bash_success_and_empty(tmp_path: Path) -> None:
    """Verifies successful command execution and empty output case."""
    # Standard output
    res = await handle_bash({"command": "echo 'Magitech Harness'"})
    assert res == "Magitech Harness"

    # Command with explicit valid cwd
    res_cwd = await handle_bash({"command": "pwd", "cwd": str(tmp_path)})
    assert res_cwd == str(tmp_path)

    # Command with no output
    res_empty = await handle_bash({"command": "true"})
    assert res_empty == "(Command executed with no output)"


@pytest.mark.asyncio
async def test_handle_bash_failure() -> None:
    """Verifies handling of non-zero exit codes."""
    # Failure with stderr
    res = await handle_bash({"command": "echo 'an error' >&2; exit 1"})
    assert "Command failed with exit code 1:" in res
    assert "an error" in res

    # Failure with stdout
    res_stdout = await handle_bash({"command": "echo 'stdout fail'; exit 2"})
    assert "Command failed with exit code 2:" in res_stdout
    assert "stdout fail" in res_stdout

    # Failure with neither stderr nor stdout
    res_none = await handle_bash({"command": "exit 3"})
    assert "Command failed with exit code 3:" in res_none
    assert "No output produced" in res_none


@pytest.mark.asyncio
async def test_handle_bash_timeout() -> None:
    """Verifies handling when a command times out."""
    # Using 10ms timeout on a command that sleeps
    res = await handle_bash({"command": "sleep 2", "timeout_ms": 10})
    assert "Command timed out" in res


@pytest.mark.asyncio
async def test_handle_bash_timeout_kill_oserror() -> None:
    """Verifies handling when proc.kill raises OSError during timeout."""
    mock_proc = Mock()
    mock_proc.kill = Mock(side_effect=OSError("Process already dead"))

    async def _mock_timeout(coro, timeout: float) -> None:
        raise TimeoutError()

    with (
        patch("asyncio.create_subprocess_shell", return_value=mock_proc),
        patch("asyncio.wait_for", side_effect=_mock_timeout),
    ):
        res = await handle_bash({"command": "sleep 10", "timeout_ms": 50})
        assert "Command timed out" in res


@pytest.mark.asyncio
async def test_bash_plugin_integration() -> None:
    """Verifies mounting bash plugin onto Context."""
    ctx = Context()
    ctx.plugin(ToolService)
    ctx.plugin(apply)
    await ctx.flush()

    assert ctx.tools.get("bash") is not None
    tool = ctx.tools.get("bash")
    assert tool is not None
    assert tool.name == "bash"
