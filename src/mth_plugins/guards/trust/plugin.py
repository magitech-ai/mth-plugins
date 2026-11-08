"""Anima plugin entry point for workspace-trust-gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anima import Context

from mth_plugins.guards.trust.gate import WorkspaceTrustGate


def apply(
    ctx: Context,
    store_path: Path | str | None = None,
    **kwargs: Any,
) -> None:
    """Anima plugin mounting WorkspaceTrustGate onto the context."""
    ctx.plugin(WorkspaceTrustGate, store_path=store_path)
