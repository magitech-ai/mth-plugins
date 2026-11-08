"""Unit tests for LspService lifecycle, routing, and diagnostic formatting."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anima import Context

from mth_plugins.bridges.lsp.service import LspService


@pytest.fixture
def ctx() -> Context:
    return Context()


def test_get_server_command(ctx: Context, tmp_path: Path) -> None:
    svc = LspService(ctx, tmp_path)
    # Unknown extension
    assert svc.get_server_command(".xyz") is None

    # Known extension when binary on PATH
    with patch(
        "shutil.which",
        side_effect=lambda b: "/bin/" + b if b == "pyright-langserver" else None,
    ):
        res = svc.get_server_command(".py")
        assert res is not None
        assert res[0] == "python"
        assert res[1] == ["pyright-langserver", "--stdio"]

    # Known extension when no binary on PATH
    with patch("shutil.which", return_value=None):
        assert svc.get_server_command(".py") is None


@pytest.mark.asyncio
async def test_get_or_create_client(ctx: Context, tmp_path: Path) -> None:
    svc = LspService(ctx, tmp_path)

    # 1. Unknown extension
    assert await svc.get_or_create_client(".unknown") is None

    # 2. Client start succeeds
    with (
        patch.object(
            svc, "get_server_command", return_value=("python", ["pyright", "--stdio"])
        ),
        patch(
            "mth_plugins.bridges.lsp.service.LspClient.start",
            new=AsyncMock(return_value=True),
        ),
    ):
        client = await svc.get_or_create_client(".py")
        assert client is not None
        assert client.language_id == "python"

        # Cached client with active process
        client._process = MagicMock()
        client2 = await svc.get_or_create_client(".py")
        assert client2 is client

        # Cached client with terminated process (process is None)
        client._process = None
        client3 = await svc.get_or_create_client(".py")
        assert client3 is not None

    # 3. Client start fails
    svc._clients.clear()
    with (
        patch.object(
            svc, "get_server_command", return_value=("python", ["pyright", "--stdio"])
        ),
        patch(
            "mth_plugins.bridges.lsp.service.LspClient.start",
            new=AsyncMock(return_value=False),
        ),
    ):
        assert await svc.get_or_create_client(".py") is None


def test_format_diagnostics(ctx: Context, tmp_path: Path) -> None:
    svc = LspService(ctx, tmp_path)
    # Empty
    assert svc.format_diagnostics([], "foo.py") == ""

    # Multi-severity
    diags = [
        {
            "range": {"start": {"line": 4, "character": 9}},
            "severity": 1,
            "message": "Syntax error",
        },
        {
            "range": {"start": {"line": 10, "character": 0}},
            "severity": 2,
            "message": "Unused import",
        },
        {
            "range": {"start": {"line": 15, "character": 4}},
            "severity": 3,
            "message": "Refactoring tip",
        },
        {
            "range": {"start": {"line": 20, "character": 2}},
            "severity": 4,
            "message": "Inline hint",
        },
        {"range": {}, "severity": 99, "message": "Unknown severity"},
    ]
    formatted = svc.format_diagnostics(diags, "foo.py")
    assert '<diagnostics file="foo.py">' in formatted
    assert "ERROR [5:10] Syntax error" in formatted
    assert "WARNING [11:1] Unused import" in formatted
    assert "INFO [16:5] Refactoring tip" in formatted
    assert "HINT [21:3] Inline hint" in formatted
    assert "ERROR [1:1] Unknown severity" in formatted
    assert "</diagnostics>" in formatted


@pytest.mark.asyncio
async def test_get_definition_and_references(ctx: Context, tmp_path: Path) -> None:
    svc = LspService(ctx, tmp_path)
    f = tmp_path / "app.py"

    # 1. No client available
    with patch.object(svc, "get_or_create_client", new=AsyncMock(return_value=None)):
        assert "No language server available" in await svc.get_definition(f, 0, 0)
        assert "No language server available" in await svc.get_references(f, 0, 0)

    # 2. Client returns result
    mock_client = MagicMock()
    mock_client.get_definition = AsyncMock(
        return_value={"uri": "file:///app.py", "range": {}}
    )
    mock_client.get_references = AsyncMock(return_value=[{"uri": "file:///app.py"}])

    with patch.object(
        svc, "get_or_create_client", new=AsyncMock(return_value=mock_client)
    ):
        res_def = await svc.get_definition(f, 1, 1)
        assert "file:///app.py" in res_def

        res_ref = await svc.get_references(f, 1, 1)
        assert "file:///app.py" in res_ref

    # 3. Client returns empty result
    mock_client.get_definition = AsyncMock(return_value=None)
    mock_client.get_references = AsyncMock(return_value=[])

    with patch.object(
        svc, "get_or_create_client", new=AsyncMock(return_value=mock_client)
    ):
        assert await svc.get_definition(f, 1, 1) == "Definition not found."
        assert await svc.get_references(f, 1, 1) == "No references found."

    # 4. Client raises exception
    mock_client.get_definition = AsyncMock(side_effect=RuntimeError("LSP timeout"))
    mock_client.get_references = AsyncMock(side_effect=RuntimeError("LSP timeout"))

    with patch.object(
        svc, "get_or_create_client", new=AsyncMock(return_value=mock_client)
    ):
        assert "LSP Definition Error" in await svc.get_definition(f, 1, 1)
        assert "LSP References Error" in await svc.get_references(f, 1, 1)


@pytest.mark.asyncio
async def test_stop_all(ctx: Context, tmp_path: Path) -> None:
    svc = LspService(ctx, tmp_path)
    c1 = MagicMock()
    c1.stop = AsyncMock()
    svc._clients["python"] = c1

    await svc.stop_all()
    c1.stop.assert_awaited_once()
    assert svc._clients == {}
