"""Unit tests for session title package exports."""

import mth_plugins.sessions.title as title_pkg


def test_init_exports() -> None:
    assert hasattr(title_pkg, "SessionTitleService")
    assert hasattr(title_pkg, "SessionTitleState")
    assert hasattr(title_pkg, "apply")
    assert hasattr(title_pkg, "clean_llm_title")
    assert hasattr(title_pkg, "extract_fallback_title")
    assert hasattr(title_pkg, "normalize_title_text")
    assert hasattr(title_pkg, "truncate_bytes")
