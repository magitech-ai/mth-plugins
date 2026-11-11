"""Unit tests for LSP bridge component registration and waterfall execution."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anima import Context
from magitech_harness.tools.service import ToolCallData, ToolService

from mth_plugins.bridges.lsp.component import apply


@pytest.fixture
def ctx() -> Context:
    context = Context()
    ToolService(context)
    return context


@pytest.mark.asyncio
async def test_component_apply_and_tools_registration(
    ctx: Context, tmp_path: Path
) -> None:
    service = apply(ctx, workspace_root=tmp_path)
    assert service is not None

    tools_svc: ToolService = ctx.tools
    assert tools_svc.get("lsp_definition") is not None
    assert tools_svc.get("lsp_references") is not None

    # Test lsp_definition execution with absolute and relative paths
    with patch.object(
        service, "get_definition", new=AsyncMock(return_value="Def found at line 10")
    ):
        call_abs = ToolCallData(
            call_id="c_def1",
            name="lsp_definition",
            arguments={"path": str(tmp_path / "main.py"), "line": 5, "character": 2},
        )
        res_abs = await tools_svc.execute(call_abs)
        assert res_abs.content == "Def found at line 10"

        call_rel = ToolCallData(
            call_id="c_def2",
            name="lsp_definition",
            arguments={"path": "main.py", "line": 5, "character": 2},
        )
        res_rel = await tools_svc.execute(call_rel)
        assert res_rel.content == "Def found at line 10"

    # Test lsp_references execution with relative and absolute paths
    with patch.object(
        service, "get_references", new=AsyncMock(return_value="Ref 1, Ref 2")
    ):
        call_ref_rel = ToolCallData(
            call_id="c_ref1",
            name="lsp_references",
            arguments={"path": "relative.py", "line": 5, "character": 2},
        )
        res_ref1 = await tools_svc.execute(call_ref_rel)
        assert res_ref1.content == "Ref 1, Ref 2"

        call_ref_abs = ToolCallData(
            call_id="c_ref2",
            name="lsp_references",
            arguments={
                "path": str(tmp_path / "relative.py"),
                "line": 5,
                "character": 2,
            },
        )
        res_ref2 = await tools_svc.execute(call_ref_abs)
        assert res_ref2.content == "Ref 1, Ref 2"


@pytest.mark.asyncio
async def test_component_post_execute_diagnostics_hook(
    ctx: Context, tmp_path: Path
) -> None:
    service = apply(ctx, workspace_root=tmp_path)

    # 1. Non-file tool -> untouched
    bash_call = ToolCallData(call_id="c1", name="bash", arguments={"command": "ls"})
    res1 = await ctx.waterfall("tools/post-execute", "bash output", bash_call)
    assert res1 == "bash output"

    # 2. File tool without path argument -> untouched
    call_no_path = ToolCallData(call_id="c2", name="write_file", arguments={})
    res2 = await ctx.waterfall("tools/post-execute", "wrote", call_no_path)
    assert res2 == "wrote"

    # 3. File does not exist -> untouched
    call_missing = ToolCallData(
        call_id="c3", name="write_file", arguments={"path": "missing.py"}
    )
    res3 = await ctx.waterfall("tools/post-execute", "wrote missing", call_missing)
    assert res3 == "wrote missing"

    # 4. Target file exists, but no client available
    py_file = tmp_path / "hello.py"
    py_file.write_text("print('hello')\n", encoding="utf-8")
    call_file = ToolCallData(
        call_id="c4", name="edit_file", arguments={"path": "hello.py"}
    )

    with patch.object(
        service, "get_or_create_client", new=AsyncMock(return_value=None)
    ):
        res4 = await ctx.waterfall("tools/post-execute", "Updated hello.py", call_file)
        assert res4 == "Updated hello.py"

    # 5. File unreadable (OSError) -> untouched
    with (
        patch.object(
            service, "get_or_create_client", new=AsyncMock(return_value=MagicMock())
        ),
        patch.object(Path, "read_text", side_effect=OSError("Permission denied")),
    ):
        res5 = await ctx.waterfall("tools/post-execute", "Updated hello.py", call_file)
        assert res5 == "Updated hello.py"

    # 6. Diagnostics returned -> appended to result
    mock_client = MagicMock()
    mock_client.notify_document = AsyncMock()
    mock_client.wait_for_diagnostics = AsyncMock(
        return_value=[
            {
                "range": {"start": {"line": 0, "character": 0}},
                "severity": 1,
                "message": "Syntax error",
            }
        ]
    )

    with patch.object(
        service, "get_or_create_client", new=AsyncMock(return_value=mock_client)
    ):
        res6 = await ctx.waterfall("tools/post-execute", "Updated hello.py", call_file)
        assert "Updated hello.py" in res6
        assert '<diagnostics file="hello.py">' in res6
        assert "ERROR [1:1] Syntax error" in res6

        # With absolute path and empty diagnostics list
        call_abs = ToolCallData(
            call_id="c_abs", name="write_file", arguments={"path": str(py_file)}
        )
        mock_client.wait_for_diagnostics = AsyncMock(return_value=[])
        res_empty = await ctx.waterfall("tools/post-execute", "Wrote abs", call_abs)
        assert res_empty == "Wrote abs"

    # 7. Exception in notify/wait -> returns original result safely
    mock_client.wait_for_diagnostics = AsyncMock(side_effect=RuntimeError("LSP crash"))
    with patch.object(
        service, "get_or_create_client", new=AsyncMock(return_value=mock_client)
    ):
        res7 = await ctx.waterfall("tools/post-execute", "Updated hello.py", call_file)
        assert res7 == "Updated hello.py"


def test_component_apply_without_tool_service(tmp_path: Path) -> None:
    empty_ctx = Context()
    svc = apply(empty_ctx, workspace_root=tmp_path)
    assert svc is not None
