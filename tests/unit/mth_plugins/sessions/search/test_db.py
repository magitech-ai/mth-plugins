"""Unit tests for SQLite FTS5 database setup, triggers, and query execution."""

from pathlib import Path
from unittest.mock import MagicMock

from mth_plugins.sessions.search.db import (
    get_db_connection,
    init_db,
    sanitize_fts_query,
    search_messages,
)


def test_db_connection_and_init(tmp_path: Path) -> None:
    db_file = tmp_path / "subdir" / "test.db"
    conn = get_db_connection(db_file)
    init_db(conn)
    # Calling init_db again is idempotent
    init_db(conn)

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    assert "conversations" in tables
    assert "messages" in tables
    assert "messages_fts" in tables
    conn.close()


def test_sanitize_fts_query() -> None:
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("   !@#$%^   ") == ""
    sanitized = sanitize_fts_query("hello world, test-term!")
    assert '"hello"*' in sanitized
    assert '"world"*' in sanitized
    assert '"test"*' in sanitized
    assert '"term"*' in sanitized


def test_fts5_triggers_and_search(tmp_path: Path) -> None:
    conn = get_db_connection(tmp_path / "search.db")
    init_db(conn)

    # 1. Insert conversation
    conn.execute(
        """
        INSERT INTO conversations (conversation_id, title, updated_at)
        VALUES ('conv-1', 'Build Compiler', '2026-11-08T00:00:00Z');
        """
    )
    # 2. Insert messages (triggers insert into messages_fts)
    conn.execute(
        """
        INSERT INTO messages (
            conversation_id, step_index, role, type, content, tool_names
        ) VALUES (
            'conv-1', 1, 'user', 'user/message',
            'How do I optimize AST parsing?', NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO messages (
            conversation_id, step_index, role, type, content, tool_names
        ) VALUES (
            'conv-1', 2, 'assistant', 'assistant/message',
            'Use Pratt parser algorithm.', 'read_file'
        );
        """
    )
    conn.commit()

    # Search term matching user message
    results = search_messages(conn, "optimize AST")
    assert len(results) == 1
    assert results[0]["conversation_id"] == "conv-1"
    assert results[0]["title"] == "Build Compiler"
    assert "AST" in results[0]["snippet"]

    # Search term matching tool name
    results_tool = search_messages(conn, "read_file")
    assert len(results_tool) == 1
    assert results_tool[0]["role"] == "assistant"

    # Search term matching conversation title
    results_title = search_messages(conn, "Compiler")
    assert len(results_title) == 2

    # 3. Update message (trigger messages_au)
    conn.execute(
        "UPDATE messages SET content = 'Use Recursive Descent parser.' WHERE id = 2;"
    )
    conn.commit()
    assert len(search_messages(conn, "Recursive Descent")) == 1
    assert len(search_messages(conn, "Pratt")) == 0

    # 4. Delete message (trigger messages_ad)
    conn.execute("DELETE FROM messages WHERE id = 2;")
    conn.commit()
    assert len(search_messages(conn, "Recursive Descent")) == 0

    # 5. Empty or punctuation query
    assert search_messages(conn, "!@#$") == []

    # 6. OperationalError handled cleanly
    mem_conn = get_db_connection(":memory:")
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = mem_conn.OperationalError("Mock error")
    assert search_messages(mock_conn, "test") == []
    mem_conn.close()

    conn.close()
