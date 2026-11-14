"""Component entry point registering snapshot bridge tools and turn hooks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from anima import Context
from anima.events import EventMode
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.bridges.workspace_snapshot.service import SnapshotService


def apply(
    ctx: Context,
    config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> SnapshotService:
    """Mounts the snapshot bridge service, tools, and waterfall hooks."""
    cfg = {**(config or {}), **kwargs}
    service = SnapshotService(ctx, cfg)

    async def _on_agent_turn(
        turn_dict: dict[str, Any],
        next_fn: Callable[..., Awaitable[Any]],
    ) -> Any:
        turn_id = str(turn_dict.get("turn_id", ""))
        result = await next_fn(turn_dict)
        if turn_id:
            await service.capture(turn_id)
        return result

    ctx.on("agent/turn", _on_agent_turn, mode=EventMode.WATERFALL)

    tools_svc: ToolService | None = getattr(ctx, "tools", None)
    if tools_svc is not None:

        async def _handle_diff(args: dict[str, Any]) -> dict[str, Any]:
            target = str(args.get("target_snapshot", "latest"))
            ws_str = args.get("workspace")
            ws = Path(str(ws_str)) if ws_str else None
            diff_text = await service.diff(target_snapshot=target, workspace=ws)
            return {
                "success": True,
                "target_snapshot": target,
                "diff": diff_text,
            }

        async def _handle_restore(args: dict[str, Any]) -> dict[str, Any]:
            cid = str(args.get("snapshot_id", "latest"))
            ws_str = args.get("workspace")
            ws = Path(str(ws_str)) if ws_str else None
            success = await service.restore(cid, workspace=ws)
            return {
                "success": success,
                "snapshot_id": cid,
            }

        tools_svc.register(
            Tool(
                name="snapshot_diff",
                description="Show unified diff between snapshot and current workspace.",
                parameters={
                    "target_snapshot": {
                        "type": "string",
                        "description": "Snapshot ID or 'latest' (default).",
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Optional workspace root path override.",
                    },
                },
                handler=_handle_diff,
            )
        )

        tools_svc.register(
            Tool(
                name="snapshot_restore",
                description="Restore workspace files to a specific snapshot state.",
                parameters={
                    "snapshot_id": {
                        "type": "string",
                        "description": "Snapshot ID or 'latest' to restore.",
                        "required": True,
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Optional workspace root path override.",
                    },
                },
                handler=_handle_restore,
            )
        )

    return service
