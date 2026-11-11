"""Anima component entry point for context compaction guardrail."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from anima import Context
from anima.events import EventMode

from mth_plugins.guards.compaction.compaction import (
    compact_session,
    estimate_history_tokens,
)


def apply(ctx: Context, config: dict | None = None, **kwargs: Any) -> None:
    """Anima component registering compaction guardrail and session/compact handler."""
    cfg = {**(config or {}), **kwargs}
    max_tokens: int = cfg.get("max_tokens", 8000)
    target_ratio: float = cfg.get("target_ratio", 0.5)

    async def _on_session_compact(
        payload: dict[str, Any], next_fn: Callable[..., Any]
    ) -> dict[str, Any]:
        session = payload.get("session")
        if session is None and ctx.has("sessions"):
            session = getattr(ctx.sessions, "active_session", None)
        if session is None:
            no_sess_res = await next_fn(
                {**payload, "compacted": False, "error": "No session provided"}
            )
            return cast(dict[str, Any], no_sess_res)

        res = await compact_session(ctx, session, target_ratio=target_ratio)
        compact_res = await next_fn({**payload, **res})
        return cast(dict[str, Any], compact_res)

    async def _on_pre_step(
        payload: dict[str, Any], next_fn: Callable[..., Any]
    ) -> dict[str, Any]:
        session = payload.get("session")
        if session is not None and ctx.has("sessions"):
            est_tokens = estimate_history_tokens(session.events)
            if est_tokens > max_tokens:
                await compact_session(ctx, session, target_ratio=target_ratio)
        pre_step_res = await next_fn(payload)
        return cast(dict[str, Any], pre_step_res)

    ctx.on("session/compact", _on_session_compact, mode=EventMode.WATERFALL)
    ctx.on("agent/pre-step", _on_pre_step, mode=EventMode.WATERFALL)


apply.inject = ["sessions"]  # type: ignore[attr-defined]
