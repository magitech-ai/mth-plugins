"""Component entry point registering the subagent delegation tool triad."""

from __future__ import annotations

from typing import Any

from anima import Context
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.subagent.manager import SubagentManager
from mth_plugins.tools.subagent.types import SubagentSpec


def apply(ctx: Context) -> SubagentManager:
    """Mounts the subagent orchestrator and registers the delegation triad tools."""
    manager = SubagentManager(ctx)

    tools_svc: ToolService | None = getattr(ctx, "tools", None)
    if tools_svc is not None:

        async def _handle_invoke(args: dict[str, Any]) -> dict[str, Any]:
            role = str(args.get("role", "worker"))
            prompt = str(args.get("prompt", ""))
            agent_name = args.get("agent_name")
            model = str(args.get("model", "inherit"))
            workspace = str(args.get("workspace", "inherit"))
            allowed = args.get("allowed_tools")
            allowed_tools = frozenset(allowed) if allowed is not None else None
            wait = bool(args.get("wait", True))

            spec = SubagentSpec(
                role=role,
                prompt=prompt,
                agent_name=str(agent_name) if agent_name else None,
                model=model,
                workspace="branch" if workspace == "branch" else "inherit",
                allowed_tools=allowed_tools,
                wait=wait,
            )
            records = await manager.invoke([spec])
            return {
                "success": True,
                "subagents": [r.to_dict() for r in records],
            }

        async def _handle_message(args: dict[str, Any]) -> dict[str, Any]:
            subagent_id = str(args.get("subagent_id", ""))
            message = str(args.get("message", ""))
            rec = await manager.send_message(subagent_id, message)
            return {
                "success": True,
                "subagent": rec.to_dict(),
            }

        async def _handle_manage(args: dict[str, Any]) -> dict[str, Any]:
            action = str(args.get("action", "list"))
            subagent_ids = args.get("subagent_ids")
            ids = [str(x) for x in subagent_ids] if subagent_ids is not None else None
            records = await manager.manage(action, ids)
            return {
                "success": True,
                "action": action,
                "subagents": [r.to_dict() for r in records],
            }

        tools_svc.register(
            Tool(
                name="invoke_subagent",
                description="Spawn and coordinate one or more delegated subagents.",
                parameters={
                    "role": {
                        "type": "string",
                        "description": "Functional role (e.g. Codebase Researcher).",
                        "required": True,
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Task prompt instruction for the subagent.",
                        "required": True,
                    },
                    "agent_name": {
                        "type": "string",
                        "description": "Optional custom agent name.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Model identifier ('inherit' or specific).",
                    },
                    "workspace": {
                        "type": "string",
                        "enum": ["inherit", "branch"],
                        "description": "Isolation mode ('inherit' or 'branch').",
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of allowed tool names.",
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "Whether to wait synchronously for turn.",
                    },
                },
                handler=_handle_invoke,
            )
        )

        tools_svc.register(
            Tool(
                name="send_message",
                description="Send follow-up conversational instruction to subagent.",
                parameters={
                    "subagent_id": {
                        "type": "string",
                        "description": "Target subagent identifier.",
                        "required": True,
                    },
                    "message": {
                        "type": "string",
                        "description": "Message instruction content.",
                        "required": True,
                    },
                },
                handler=_handle_message,
            )
        )

        tools_svc.register(
            Tool(
                name="manage_subagents",
                description="Inspect or terminate active subagents.",
                parameters={
                    "action": {
                        "type": "string",
                        "enum": ["list", "kill", "kill_all"],
                        "description": "Management action to perform.",
                        "required": True,
                    },
                    "subagent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target subagent identifiers for kill action.",
                    },
                },
                handler=_handle_manage,
            )
        )

    return manager
