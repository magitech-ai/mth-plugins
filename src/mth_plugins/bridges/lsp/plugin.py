"""Anima plugin entry point for Language Server Protocol (LSP) diagnostics and tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from anima import Context
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolCallData

from mth_plugins.bridges.lsp.service import LspService


def apply(
    ctx: Context,
    workspace_root: Path | None = None,
    **kwargs: Any,
) -> LspService:
    """Mounts the LSP bridge service, diagnostics hook, and navigation tools."""
    root = (workspace_root or Path.cwd()).resolve()
    service = LspService(ctx, root)

    # Register disposer effect
    ctx.effect(lambda: service.stop_all)

    # 1. Post-execute diagnostics waterfall hook
    async def _post_execute_diagnostics(
        output: Any,
        call_data: ToolCallData,
        next_fn: Callable[..., Any],
    ) -> Any:
        res = await next_fn(output, call_data)
        if call_data.name not in ("edit_file", "write_file", "edit", "write"):
            return res

        path_val = call_data.arguments.get("path")
        if not path_val:
            return res

        file_path = Path(str(path_val))
        if not file_path.is_absolute():
            file_path = root / file_path

        if not file_path.is_file():
            return res

        client = await service.get_or_create_client(file_path.suffix.lower())
        if client is None:
            return res

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            return res

        try:
            await client.notify_document(file_path, content)
            uri = file_path.resolve().as_uri()
            diagnostics = await client.wait_for_diagnostics(
                uri, debounce_ms=150, timeout_ms=3000
            )
            diag_text = service.format_diagnostics(diagnostics, str(path_val))
            if diag_text:
                return f"{res}\n\n{diag_text}"
        except Exception:
            pass

        return res

    ctx.on("tools/post-execute", _post_execute_diagnostics)

    # 2. Active tools registration
    tools_svc = getattr(ctx, "tools", None)
    if tools_svc is not None and hasattr(tools_svc, "register"):

        async def _lsp_definition(args: dict[str, Any]) -> str:
            p = Path(str(args.get("path", "")))
            if not p.is_absolute():
                p = root / p
            line = int(args.get("line", 0))
            char = int(args.get("character", 0))
            return await service.get_definition(p, line, char)

        async def _lsp_references(args: dict[str, Any]) -> str:
            p = Path(str(args.get("path", "")))
            if not p.is_absolute():
                p = root / p
            line = int(args.get("line", 0))
            char = int(args.get("character", 0))
            return await service.get_references(p, line, char)

        tools_svc.register(
            Tool(
                name="lsp_definition",
                description="Find symbol definition location using LSP.",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "Target file path.",
                        "required": True,
                    },
                    "line": {
                        "type": "integer",
                        "description": "Zero-indexed line number.",
                        "required": True,
                    },
                    "character": {
                        "type": "integer",
                        "description": "Zero-indexed column character.",
                        "required": True,
                    },
                },
                handler=_lsp_definition,
            )
        )

        tools_svc.register(
            Tool(
                name="lsp_references",
                description="Find all references to symbol at location via LSP.",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "Target file path.",
                        "required": True,
                    },
                    "line": {
                        "type": "integer",
                        "description": "Zero-indexed line number.",
                        "required": True,
                    },
                    "character": {
                        "type": "integer",
                        "description": "Zero-indexed column character.",
                        "required": True,
                    },
                },
                handler=_lsp_references,
            )
        )

    return service


apply.inject = ["tools"]  # type: ignore[attr-defined]
