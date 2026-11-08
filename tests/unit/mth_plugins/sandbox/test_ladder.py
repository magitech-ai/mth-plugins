"""Unit tests for sandbox privilege ladder and containment."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from anima import Context
from magitech_harness.shell.service import ShellResult

from mth_plugins.sandbox.ladder import (
    PrivilegeLevel,
    PrivilegeViolationError,
    SandboxDiagnostics,
    SandboxService,
    SandboxUnavailableError,
    build_bubblewrap_command,
    find_bubblewrap,
)


def test_find_bubblewrap(tmp_path: Path) -> None:
    # Custom existing file
    custom_bin = tmp_path / "custom-bwrap"
    custom_bin.write_text("#!/bin/sh\nexit 0\n")
    assert find_bubblewrap(str(custom_bin)) == str(custom_bin)

    # Custom non-existing file
    assert find_bubblewrap(str(tmp_path / "non-existent")) is None

    # Fallback to PATH lookup
    with patch("shutil.which", return_value="/usr/bin/bwrap"):
        assert find_bubblewrap() == "/usr/bin/bwrap"


def test_build_bubblewrap_command_modes(tmp_path: Path) -> None:
    # 1. STRICT mode with str command
    cmd_strict = build_bubblewrap_command(
        "/usr/bin/bwrap",
        "echo hello",
        cwd=tmp_path,
        level=PrivilegeLevel.STRICT,
    )
    assert "--die-with-parent" in cmd_strict
    assert "--unshare-net" in cmd_strict
    assert "--bind" in cmd_strict
    assert str(tmp_path.resolve()) in cmd_strict
    assert cmd_strict[-3:] == ["/bin/sh", "-c", "echo hello"]

    # 2. READONLY mode with cwd
    cmd_ro = build_bubblewrap_command(
        "/usr/bin/bwrap",
        ["ls", "-la"],
        cwd=tmp_path,
        level=PrivilegeLevel.READONLY,
    )
    assert "--ro-bind" in cmd_ro
    assert str(tmp_path.resolve()) in cmd_ro
    assert cmd_ro[-2:] == ["ls", "-la"]

    # 3. NETWORK mode without cwd
    cmd_net = build_bubblewrap_command(
        "/usr/bin/bwrap",
        "curl https://example.com",
        cwd=None,
        level=PrivilegeLevel.NETWORK,
    )
    assert "--unshare-net" not in cmd_net
    assert "/etc/resolv.conf" in cmd_net
    assert cmd_net[-3:] == ["/bin/sh", "-c", "curl https://example.com"]


def test_sandbox_service_diagnostics() -> None:
    ctx = Context()
    svc = SandboxService(
        ctx,
        max_level=PrivilegeLevel.STRICT,
        enforce=False,
        bwrap_path="/usr/bin/bwrap",
    )
    with patch("sys.platform", "linux"):
        svc.bwrap_path = "/usr/bin/bwrap"
        assert svc.is_available() is True
        diag = svc.get_diagnostics()
        assert isinstance(diag, SandboxDiagnostics)
        assert diag.isolation_backend == "bubblewrap"
        assert diag.bwrap_available is True

    with patch("sys.platform", "win32"):
        assert svc.is_available() is False
        diag_win = svc.get_diagnostics()
        assert diag_win.isolation_backend == "none"


def test_sandbox_validate_privilege() -> None:
    ctx = Context()
    svc = SandboxService(ctx, max_level=PrivilegeLevel.STRICT)

    # Valid: READONLY <= STRICT, STRICT <= STRICT
    svc.validate_privilege(PrivilegeLevel.READONLY)
    svc.validate_privilege(PrivilegeLevel.STRICT)

    # Verify NETWORK exceeds permitted budget
    with pytest.raises(PrivilegeViolationError, match="exceeds permitted maximum"):
        svc.validate_privilege(PrivilegeLevel.NETWORK)


def test_sandbox_wrap_command_unrestricted(tmp_path: Path) -> None:
    ctx = Context()
    svc = SandboxService(ctx, max_level=PrivilegeLevel.UNRESTRICTED)

    # String command
    assert svc.wrap_command("ls -la", cwd=tmp_path) == ["/bin/sh", "-c", "ls -la"]
    # List command
    assert svc.wrap_command(["ls", "-la"], cwd=tmp_path) == ["ls", "-la"]


def test_sandbox_wrap_command_unavailable_fallback_and_enforce(tmp_path: Path) -> None:
    ctx = Context()

    # Fallback mode (enforce=False)
    svc_fallback = SandboxService(ctx, max_level=PrivilegeLevel.STRICT, enforce=False)
    with patch.object(svc_fallback, "is_available", return_value=False):
        wrapped_str = svc_fallback.wrap_command("ls", cwd=tmp_path)
        assert wrapped_str == ["/bin/sh", "-c", "ls"]
        wrapped_list = svc_fallback.wrap_command(["echo", "hi"], cwd=tmp_path)
        assert wrapped_list == ["echo", "hi"]

    # Enforce mode (enforce=True) -> raises SandboxUnavailableError
    svc_enforce = SandboxService(ctx, max_level=PrivilegeLevel.STRICT, enforce=True)
    with (
        patch.object(svc_enforce, "is_available", return_value=False),
        pytest.raises(SandboxUnavailableError, match="Bubblewrap is unavailable"),
    ):
        svc_enforce.wrap_command("ls", cwd=tmp_path)


def test_sandbox_wrap_command_available(tmp_path: Path) -> None:
    ctx = Context()
    svc = SandboxService(ctx, max_level=PrivilegeLevel.STRICT)
    with patch.object(svc, "is_available", return_value=True):
        svc.bwrap_path = "/usr/bin/bwrap"
        cmd = svc.wrap_command("whoami", cwd=tmp_path)
        assert cmd[0] == "/usr/bin/bwrap"
        assert "whoami" in cmd[-1]


async def test_sandbox_run_success(tmp_path: Path) -> None:
    ctx = Context()
    svc = SandboxService(ctx, max_level=PrivilegeLevel.STRICT)

    # Mock ctx.shell
    mock_shell = AsyncMock()
    mock_shell.run.return_value = ShellResult(
        exit_code=0,
        stdout="sandboxed output",
        stderr="",
        timed_out=False,
        aborted=False,
        bytes_read=16,
    )
    ctx._register_service("shell", mock_shell)

    res = await svc.run("echo hello", cwd=str(tmp_path))
    assert res.exit_code == 0
    assert res.stdout == "sandboxed output"
    mock_shell.run.assert_awaited_once()


async def test_sandbox_run_no_shell_raises(tmp_path: Path) -> None:
    ctx = Context()
    svc = SandboxService(ctx, max_level=PrivilegeLevel.STRICT)
    with pytest.raises(RuntimeError, match="No shell service mounted"):
        await svc.run("echo test", cwd=tmp_path)
