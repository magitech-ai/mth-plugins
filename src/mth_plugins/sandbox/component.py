"""Anima component entry point for sandbox-ladder."""

from __future__ import annotations

from typing import Any

from anima import Context

from mth_plugins.sandbox.ladder import PrivilegeLevel, SandboxService


def apply(
    ctx: Context,
    max_level: str = "strict",
    enforce: bool = False,
    bwrap_path: str | None = None,
    **kwargs: Any,
) -> None:
    """Anima component registering the SandboxService onto the context."""
    level = PrivilegeLevel(max_level.lower())
    ctx.use(
        SandboxService,
        max_level=level,
        enforce=enforce,
        bwrap_path=bwrap_path,
    )
