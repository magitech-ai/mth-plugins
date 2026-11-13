"""Context compaction logic and history folding algorithms."""

from __future__ import annotations

import logging
from typing import Any

from anima import Context
from magitech_harness.session.events import EventType, SessionEvent
from magitech_harness.session.pairing import is_tool_pairing_balanced
from magitech_harness.session.store import Session

logger = logging.getLogger("mth_plugins.guards.compaction")

_RETIRED_COMPACTION_TYPE = "session/compaction"
"""Retired summary event, read-only: old logs still carry it, and the
read side below still understands it. New summaries are written as
``compaction/summary``; the full compaction engine sequence is Phase 4."""


def estimate_tokens(text: str) -> int:
    """Estimates the number of tokens in a string using a 4-char heuristic."""
    if not text:
        return 1
    return max(1, len(text) // 4)


def estimate_history_tokens(events: list[SessionEvent]) -> int:
    """Estimates the cumulative token count of a sequence of session events."""
    total = 0
    for ev in events:
        if ev.type == EventType.USER_MESSAGE:
            total += estimate_tokens(str(ev.payload.get("text", "")))
        elif ev.type == EventType.ASSISTANT_MESSAGE:
            total += estimate_tokens(str(ev.payload.get("text", "")))
            for tc in ev.payload.get("tool_calls") or []:
                total += estimate_tokens(str(tc))
        elif ev.type == EventType.TOOL_RESULT:
            total += estimate_tokens(
                str(ev.payload.get("content", ev.payload.get("output", "")))
            )
        elif ev.type in (_RETIRED_COMPACTION_TYPE, EventType.COMPACTION_SUMMARY):
            total += estimate_tokens(str(ev.payload.get("summary", "")))
        else:
            total += 2
    return total


def find_safe_cut_index(
    events: list[SessionEvent], target_cut_index: int
) -> int | None:
    """Finds the largest safe cut boundary <= target_cut_index with balanced pairing."""
    if not events or target_cut_index <= 0:
        return None

    max_idx = min(target_cut_index, len(events) - 1)
    for cut in range(max_idx, 0, -1):
        if is_tool_pairing_balanced(events, cut - 1):
            return cut
    return None


def _format_event_bullet(ev: SessionEvent) -> str | None:
    """Formats a single session event into a readable summary bullet."""
    if ev.type == EventType.USER_MESSAGE:
        return f"- User: {ev.payload.get('text', '')}"
    if ev.type == EventType.ASSISTANT_MESSAGE:
        text = ev.payload.get("text", "")
        tc_names = [
            getattr(tc, "name", str(tc)) for tc in (ev.payload.get("tool_calls") or [])
        ]
        items = []
        if text:
            items.append(f"Assistant: {text}")
        items.extend(f"Tool call '{name}'" for name in tc_names)
        return "- " + "; ".join(items) if items else None
    if ev.type == EventType.TOOL_RESULT:
        content = ev.payload.get("content", ev.payload.get("output", ""))
        return f"- Tool result: {content}"
    if ev.type in (_RETIRED_COMPACTION_TYPE, EventType.COMPACTION_SUMMARY):
        return f"- Prior Summary: {ev.payload.get('summary', '')}"
    return None


async def summarize_events(
    events: list[SessionEvent], ctx: Context | None = None
) -> str:
    """Summarizes a slice of session events using LLM if available, else fallback."""
    bullets: list[str] = []
    for ev in events:
        bullet = _format_event_bullet(ev)
        if bullet:
            bullets.append(bullet)

    joined_bullets = "\n".join(bullets)

    if ctx is not None and ctx.has("llm") and ctx.llm.providers:
        prompt = (
            "Summarize the following conversation history concisely into a brief "
            f"context checkpoint:\n\n{joined_bullets}"
        )
        try:
            res = await ctx.llm.call(messages=[{"role": "user", "content": prompt}])
            if res.text.strip():
                return str(res.text).strip()
        except Exception as exc:
            logger.warning("LLM summarization failed (%s); using fallback", exc)

    return f"[Prior Context Summary]\n{joined_bullets}"


async def compact_session(
    ctx: Context,
    session: Session,
    *,
    target_ratio: float = 0.5,
    custom_summary: str | None = None,
) -> dict[str, Any]:
    """Compacts session history by folding prior events into a summary event.

    The summary is written as ``compaction/summary``: the retired
    ``session/compaction`` type can no longer be appended.
    """
    if len(session.events) < 2:
        return {
            "compacted": False,
            "reason": "Session history too short to compact",
        }

    target_cut = max(1, int(len(session.events) * target_ratio))
    cut_idx = find_safe_cut_index(session.events, target_cut)

    if cut_idx is None or cut_idx <= 0:
        return {
            "compacted": False,
            "reason": "No balanced boundary found for compaction",
        }

    events_to_compact = session.events[:cut_idx]
    summary = custom_summary or await summarize_events(events_to_compact, ctx=ctx)

    ctx.sessions.log_event(
        session,
        EventType.COMPACTION_SUMMARY,
        {
            "summary": summary,
            "compacted_count": cut_idx,
        },
    )

    return {
        "compacted": True,
        "compacted_count": cut_idx,
        "summary": summary,
    }
