"""Anima component entry point for output truncation guardrail."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anima import Context

from mth_plugins.guards.truncation.truncation import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    format_size,
    truncate_head,
)


def apply(ctx: Context, config: dict | None = None, **kwargs: Any) -> None:
    """Anima component applying post-execute tool truncation guardrail."""
    cfg = {**(config or {}), **kwargs}
    max_lines: int = cfg.get("max_lines", DEFAULT_MAX_LINES)
    max_bytes: int = cfg.get("max_bytes", DEFAULT_MAX_BYTES)

    async def _post_execute(
        output: Any, call_data: Any, next_fn: Callable[..., Any]
    ) -> Any:
        res = await next_fn(output, call_data)
        if not isinstance(res, str):
            return res
        trunc = truncate_head(res, max_lines=max_lines, max_bytes=max_bytes)
        if trunc.truncated:
            shown_lines = trunc.shown_end or 0
            return (
                f"{trunc.text}\n\n"
                f"[Output truncated: showing {shown_lines} of "
                f"{trunc.total_lines} lines ({format_size(max_bytes)} limit reached).]"
            )
        return res

    ctx.on("tools/post-execute", _post_execute)


apply.inject = ["tools"]  # type: ignore[attr-defined]
