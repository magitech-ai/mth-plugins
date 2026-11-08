"""Tests for LSP bridge package exports."""

import mth_plugins.bridges.lsp as lsp_pkg


def test_init_exports() -> None:
    assert hasattr(lsp_pkg, "LspClient")
    assert hasattr(lsp_pkg, "LspService")
    assert hasattr(lsp_pkg, "apply")
