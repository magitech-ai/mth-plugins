"""Unit tests for session search package exports."""

import mth_plugins.sessions.search as search_pkg


def test_init_exports() -> None:
    assert hasattr(search_pkg, "SessionIndexer")
    assert hasattr(search_pkg, "SessionSearchService")
    assert hasattr(search_pkg, "apply")
    assert hasattr(search_pkg, "get_db_connection")
    assert hasattr(search_pkg, "init_db")
    assert hasattr(search_pkg, "search_messages")
