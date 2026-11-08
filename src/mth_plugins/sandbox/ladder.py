"""Privilege ladder and Bubblewrap containment sandbox engine."""

from __future__ import annotations

import logging
import shlex
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from anima import Context, Service
from magitech_harness.shell.service import ShellResult

logger = logging.getLogger("mth_plugins.sandbox")


class PrivilegeLevel(StrEnum):
    """Privilege budgets arranged in ascending order of granted capability."""

    READONLY = "readonly"
    STRICT = "strict"
    NETWORK = "network"
    UNRESTRICTED = "unrestricted"


_PRIVILEGE_RANKS: dict[PrivilegeLevel, int] = {
    PrivilegeLevel.READONLY: 0,
    PrivilegeLevel.STRICT: 1,
    PrivilegeLevel.NETWORK: 2,
    PrivilegeLevel.UNRESTRICTED: 3,
}


class SandboxError(Exception):
    """Base error for sandbox containment failures."""


class PrivilegeViolationError(SandboxError):
    """Raised when an operation requests privileges exceeding the permitted budget."""


class SandboxUnavailableError(SandboxError):
    """Raised when sandbox isolation is required but unavailable on the host."""


@dataclass(frozen=True)
class SandboxDiagnostics:
    """Diagnostic state of the sandbox containment system."""

    platform: str
    bwrap_available: bool
    bwrap_path: str | None
    active_max_level: PrivilegeLevel
    isolation_backend: str


def find_bubblewrap(custom_path: str | None = None) -> str | None:
    """Locates the bubblewrap executable if present on the system."""
    if custom_path:
        p = Path(custom_path)
        return str(p) if p.is_file() else None
    return shutil.which("bwrap")


def build_bubblewrap_command(
    bwrap_bin: str,
    command: str | list[str],
    cwd: Path | None = None,
    level: PrivilegeLevel = PrivilegeLevel.STRICT,
) -> list[str]:
    """Assembles a Bubblewrap execution argv list for the given privilege level."""
    args: list[str] = [bwrap_bin, "--die-with-parent"]

    # System roots in read-only containment
    args.extend(
        [
            "--ro-bind-try",
            "/usr",
            "/usr",
            "--ro-bind-try",
            "/bin",
            "/bin",
            "--ro-bind-try",
            "/lib",
            "/lib",
            "--ro-bind-try",
            "/lib64",
            "/lib64",
        ]
    )

    # Isolated virtual filesystems
    args.extend(
        [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]
    )

    # Namespace isolation
    args.extend(
        [
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--unshare-cgroup-try",
        ]
    )

    # Network isolation handling
    if level == PrivilegeLevel.NETWORK:
        args.extend(
            [
                "--ro-bind-try",
                "/etc/resolv.conf",
                "/etc/resolv.conf",
                "--ro-bind-try",
                "/etc/ssl",
                "/etc/ssl",
                "--ro-bind-try",
                "/etc/pki",
                "/etc/pki",
                "--ro-bind-try",
                "/etc/hosts",
                "/etc/hosts",
            ]
        )
    else:
        args.append("--unshare-net")

    # Working directory bind
    if cwd is not None:
        target_dir = cwd.resolve()
        if level == PrivilegeLevel.READONLY:
            args.extend(["--ro-bind", str(target_dir), str(target_dir)])
        else:
            args.extend(["--bind", str(target_dir), str(target_dir)])
        args.extend(["--chdir", str(target_dir)])

    args.append("--")

    if isinstance(command, str):
        args.extend(["/bin/sh", "-c", command])
    else:
        args.extend(command)

    return args


class SandboxService(Service):
    """Service providing process sandboxing and privilege budget management."""

    def __init__(
        self,
        ctx: Context,
        max_level: PrivilegeLevel = PrivilegeLevel.STRICT,
        enforce: bool = False,
        bwrap_path: str | None = None,
    ) -> None:
        super().__init__(ctx, "sandbox")
        self.max_level = max_level
        self.enforce = enforce
        self.bwrap_path = find_bubblewrap(bwrap_path)

    def is_available(self) -> bool:
        """Returns True if a hardware/OS container sandbox backend is available."""
        return sys.platform.startswith("linux") and self.bwrap_path is not None

    def get_diagnostics(self) -> SandboxDiagnostics:
        """Returns runtime diagnostics for the active sandbox backend."""
        backend = "bubblewrap" if self.is_available() else "none"
        return SandboxDiagnostics(
            platform=sys.platform,
            bwrap_available=self.bwrap_path is not None,
            bwrap_path=self.bwrap_path,
            active_max_level=self.max_level,
            isolation_backend=backend,
        )

    def validate_privilege(self, level: PrivilegeLevel) -> None:
        """Validates that requested privilege level does not exceed maximum budget."""
        requested_rank = _PRIVILEGE_RANKS.get(level, 99)
        max_rank = _PRIVILEGE_RANKS.get(self.max_level, 1)
        if requested_rank > max_rank:
            raise PrivilegeViolationError(
                f"Requested privilege level '{level.value}' exceeds permitted "
                f"maximum '{self.max_level.value}'."
            )

    def wrap_command(
        self,
        command: str | list[str],
        cwd: Path | None = None,
        level: PrivilegeLevel | None = None,
    ) -> list[str]:
        """Wraps a shell command in sandbox isolation based on privilege level.

        Args:
            command: Command string or token list to execute.
            cwd: Optional working directory.
            level: Desired privilege level (defaults to self.max_level).

        Returns:
            Argv list ready for execution.

        Raises:
            PrivilegeViolationError: If requested level exceeds budget.
            SandboxUnavailableError: If sandbox is required and enforced
                but unavailable on the host.
        """
        target_level = level or self.max_level
        self.validate_privilege(target_level)

        if target_level == PrivilegeLevel.UNRESTRICTED:
            if isinstance(command, str):
                return ["/bin/sh", "-c", command]
            return list(command)

        if not self.is_available():
            if self.enforce:
                raise SandboxUnavailableError(
                    f"Sandbox enforcement is active, but Bubblewrap is unavailable "
                    f"on platform '{sys.platform}'."
                )
            logger.warning(
                "Sandbox isolation unavailable; falling back to direct host execution"
            )
            if isinstance(command, str):
                return ["/bin/sh", "-c", command]
            return list(command)

        assert self.bwrap_path is not None
        return build_bubblewrap_command(
            self.bwrap_path,
            command=command,
            cwd=cwd,
            level=target_level,
        )

    async def run(
        self,
        command: str,
        cwd: Path | str | None = None,
        level: PrivilegeLevel | None = None,
        **kwargs: Any,
    ) -> ShellResult:
        """Executes a command through the sandbox containment layer."""
        cwd_path = Path(cwd) if cwd else None
        wrapped_argv = self.wrap_command(command, cwd=cwd_path, level=level)
        exec_str = shlex.join(wrapped_argv)

        if self.ctx.has("shell"):
            res = await self.ctx.shell.run(exec_str, cwd=cwd_path, **kwargs)
            return res if isinstance(res, ShellResult) else ShellResult(*res)

        raise RuntimeError("No shell service mounted on context (ctx.shell).")
