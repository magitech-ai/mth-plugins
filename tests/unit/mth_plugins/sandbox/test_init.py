"""Unit tests for sandbox package exports."""

from __future__ import annotations

from mth_plugins import sandbox


def test_sandbox_exports() -> None:
    assert hasattr(sandbox, "PrivilegeLevel")
    assert hasattr(sandbox, "SandboxService")
    assert hasattr(sandbox, "SandboxDiagnostics")
    assert hasattr(sandbox, "PrivilegeViolationError")
    assert hasattr(sandbox, "SandboxUnavailableError")
    assert hasattr(sandbox, "SandboxError")
