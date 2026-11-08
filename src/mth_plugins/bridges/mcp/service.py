"""McpBridgeService: Bridges external MCP servers into ctx.tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from anima import Context, Disposer, Service
from magitech_harness.tools.definition import Tool

from mth_plugins.bridges.mcp.client import McpClient
from mth_plugins.bridges.mcp.transport import SseTransport, StdioTransport

logger = logging.getLogger("mth_plugins.bridges.mcp")


class McpBridgeService(Service):
    """Service managing MCP server processes and registering dynamic tools."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "mcp")
        self.clients: dict[str, McpClient] = {}
        self.registered_disposers: list[Disposer] = []
        self.registered_tool_names: list[str] = []

        def _cleanup() -> None:
            for d in self.registered_disposers:
                d()
            self.registered_disposers.clear()
            self.registered_tool_names.clear()

        self.ctx.effect(lambda: _cleanup)

    async def load_servers_from_config(self, config_data: dict[str, Any]) -> list[str]:
        """Loads and connects MCP servers defined in a parsed configuration."""
        servers = config_data.get("mcpServers", {})
        loaded_names: list[str] = []

        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue

            client: McpClient | None = None
            if "command" in cfg:
                transport = StdioTransport(
                    command=cfg["command"],
                    args=cfg.get("args"),
                    env=cfg.get("env"),
                    cwd=cfg.get("cwd"),
                )
                client = McpClient(transport, server_name=name)
            elif "url" in cfg:
                transport_sse = SseTransport(
                    url=cfg["url"],
                    headers=cfg.get("headers"),
                )
                client = McpClient(transport_sse, server_name=name)

            if client is None:
                continue

            try:
                await client.connect()
                self.clients[name] = client
                loaded_names.append(name)
                await self._register_server_tools(name, client)
            except Exception as e:
                logger.error("Failed to connect MCP server %s: %s", name, e)
                await client.close()

        return loaded_names

    async def _register_server_tools(self, server_name: str, client: McpClient) -> None:
        """Queries tool schemas from client and mounts them onto ctx.tools."""
        if not self.ctx.has("tools"):
            return

        tool_defs = await client.list_tools()
        for t in tool_defs:
            orig_name = t.get("name", "")
            if not orig_name:
                continue
            namespaced_name = f"mcp_{server_name}_{orig_name}"
            desc = t.get("description", f"MCP tool from {server_name}")
            params = t.get("inputSchema", {"type": "object", "properties": {}})

            def _make_handler(c: McpClient, t_name: str) -> Callable[..., Any]:
                async def _handler(args: dict[str, Any]) -> str:
                    return await c.call_tool(t_name, args)

                return _handler

            tool = Tool(
                name=namespaced_name,
                description=desc,
                parameters=params,
                handler=_make_handler(client, orig_name),
            )
            disposer = self.ctx.tools.register(tool)
            self.registered_disposers.append(disposer)
            self.registered_tool_names.append(namespaced_name)

    async def load_from_layers(self, filename: str = "mcp.json") -> list[str]:
        """Discovers mcp.json across active layers and loads all servers."""
        configs_to_load: list[Path] = []
        if self.ctx.has("layers"):
            configs_to_load = self.ctx.layers.find_all(filename)

        all_loaded: list[str] = []
        for p in configs_to_load:
            try:
                content = p.read_text(encoding="utf-8")
                data = json.loads(content)
                loaded = await self.load_servers_from_config(data)
                all_loaded.extend(loaded)
            except Exception as e:
                logger.warning("Error reading MCP config from %s: %s", p, e)

        return all_loaded

    async def close_all(self) -> None:
        """Closes all active MCP clients and unregisters tools."""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()

        for d in self.registered_disposers:
            d()
        self.registered_disposers.clear()
        self.registered_tool_names.clear()
