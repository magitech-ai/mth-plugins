"""LSP Service managing language server lifecycle and diagnostic formatting."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from anima import Context, Service

from mth_plugins.bridges.lsp.client import LspClient

SERVER_SPECS: dict[str, tuple[str, list[list[str]]]] = {
    ".py": (
        "python",
        [["basedpyright-langserver", "--stdio"], ["pyright-langserver", "--stdio"]],
    ),
    ".pyi": (
        "python",
        [["basedpyright-langserver", "--stdio"], ["pyright-langserver", "--stdio"]],
    ),
    ".ts": ("typescript", [["typescript-language-server", "--stdio"]]),
    ".tsx": ("typescript", [["typescript-language-server", "--stdio"]]),
    ".js": ("javascript", [["typescript-language-server", "--stdio"]]),
    ".jsx": ("javascript", [["typescript-language-server", "--stdio"]]),
    ".mjs": ("javascript", [["typescript-language-server", "--stdio"]]),
    ".cjs": ("javascript", [["typescript-language-server", "--stdio"]]),
    ".rs": ("rust", [["rust-analyzer"]]),
    ".go": ("go", [["gopls"]]),
}

DIAGNOSTIC_SEVERITY = {
    1: "ERROR",
    2: "WARNING",
    3: "INFO",
    4: "HINT",
}


class LspService(Service):
    """Central service managing language servers, diagnostics, and code intelligence."""

    def __init__(self, ctx: Context, workspace_root: Path | None = None) -> None:
        super().__init__(ctx, "lsp")
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self._clients: dict[str, LspClient] = {}

    def get_server_command(self, ext: str) -> tuple[str, list[str]] | None:
        """Finds language_id and executable command for given extension."""
        spec = SERVER_SPECS.get(ext)
        if not spec:
            return None

        lang_id, candidates = spec
        for cmd in candidates:
            binary = cmd[0]
            if shutil.which(binary):
                return lang_id, cmd

        return None

    async def get_or_create_client(self, ext: str) -> LspClient | None:
        """Retrieves or launches an active LSP client for the given file extension."""
        spec = self.get_server_command(ext)
        if not spec:
            return None

        lang_id, command = spec
        if lang_id in self._clients:
            client = self._clients[lang_id]
            if client._process is not None:
                return client

        client = LspClient(command, self.workspace_root, lang_id)
        started = await client.start()
        if started:
            self._clients[lang_id] = client
            return client
        return None

    def format_diagnostics(
        self, diagnostics: list[dict[str, Any]], file_path_str: str
    ) -> str:
        """Formats LSP diagnostic dictionaries into an XML block."""
        if not diagnostics:
            return ""

        lines: list[str] = [f'<diagnostics file="{file_path_str}">']
        for diag in diagnostics:
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            line_num = int(start.get("line", 0)) + 1
            col_num = int(start.get("character", 0)) + 1
            severity_num = diag.get("severity", 1)
            severity = DIAGNOSTIC_SEVERITY.get(severity_num, "ERROR")
            message = str(diag.get("message", "")).strip()
            lines.append(f"{severity} [{line_num}:{col_num}] {message}")

        lines.append("</diagnostics>")
        return "\n".join(lines)

    async def get_definition(self, file_path: Path, line: int, character: int) -> str:
        """Look up definition of symbol at the specified position."""
        ext = file_path.suffix.lower()
        client = await self.get_or_create_client(ext)
        if client is None:
            return f"No language server available for '{ext}' files."

        try:
            res = await client.get_definition(file_path, line, character)
            if not res:
                return "Definition not found."
            return str(res)
        except Exception as exc:
            return f"LSP Definition Error: {exc}"

    async def get_references(self, file_path: Path, line: int, character: int) -> str:
        """Look up all references of symbol at the specified position."""
        ext = file_path.suffix.lower()
        client = await self.get_or_create_client(ext)
        if client is None:
            return f"No language server available for '{ext}' files."

        try:
            res = await client.get_references(file_path, line, character)
            if not res:
                return "No references found."
            return str(res)
        except Exception as exc:
            return f"LSP References Error: {exc}"

    async def stop_all(self) -> None:
        """Stops all running language server clients."""
        for client in self._clients.values():
            await client.stop()
        self._clients.clear()
