"""Plugin entry point registering session title service and turn hooks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from anima import Context
from anima.events import EventMode
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.sessions.title.service import SessionTitleService


def apply(ctx: Context) -> SessionTitleService:
    """Mounts the session titling service and registers waterfall interceptors."""
    service = SessionTitleService(ctx)

    async def _on_agent_turn(
        turn_dict: dict[str, Any],
        next_fn: Callable[..., Awaitable[Any]],
    ) -> Any:
        session_id = str(turn_dict.get("session_id", "current"))
        user_input = str(turn_dict.get("user_input", ""))
        if user_input:
            await service.evaluate_turn(session_id, user_input)
        return await next_fn(turn_dict)

    ctx.on("agent/turn", _on_agent_turn, mode=EventMode.WATERFALL)

    tools_svc: ToolService | None = getattr(ctx, "tools", None)
    if tools_svc is not None:

        async def _handle_set_title(args: dict[str, Any]) -> dict[str, Any]:
            title = str(args.get("title", ""))
            session_id = str(args.get("session_id", "current"))
            service.set_title(session_id, title, pinned=True)
            return {
                "success": True,
                "session_id": session_id,
                "title": title,
            }

        tools_svc.register(
            Tool(
                name="set_session_title",
                description="Explicitly set or rename a conversation session title.",
                parameters={
                    "title": {
                        "type": "string",
                        "description": "New title for the session.",
                        "required": True,
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Target session identifier (default 'current').",
                    },
                },
                handler=_handle_set_title,
            )
        )

    return service
