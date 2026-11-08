"""Plugin entry point registering session search service and tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anima import Context
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.sessions.search.service import SessionSearchService


def apply(
    ctx: Context,
    db_path: Path | str | None = None,
) -> SessionSearchService:
    """Mounts the session search service and registers the session_search tool."""
    service = SessionSearchService(ctx, db_path=db_path)

    tools_svc: ToolService | None = getattr(ctx, "tools", None)
    if tools_svc is not None:

        async def _handle_search(args: dict[str, Any]) -> dict[str, Any]:
            query = str(args.get("query", ""))
            limit = int(args.get("limit", 10))
            matches = service.search(query, limit=limit)
            return {
                "success": True,
                "query": query,
                "count": len(matches),
                "matches": matches,
            }

        tools_svc.register(
            Tool(
                name="session_search",
                description=(
                    "Search historical conversations, messages, "
                    "and tool invocations via FTS5."
                ),
                parameters={
                    "query": {
                        "type": "string",
                        "description": "Search query terms.",
                        "required": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                    },
                },
                handler=_handle_search,
            )
        )

    # Auto-index on turn completion event
    def _on_turn_finish(session: Any, turn_id: str) -> None:
        storage_path = getattr(session, "storage_path", None)
        if storage_path is not None:
            service.indexer.index_file(Path(storage_path))

    ctx.on("turn/finish", _on_turn_finish)
    ctx.effect(lambda: service.close)

    return service
