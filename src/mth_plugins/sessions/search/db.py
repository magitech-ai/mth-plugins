"""SQLite FTS5 full-text search database engine for session logs."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


def get_db_connection(db_path: Path | str) -> sqlite3.Connection:
    """Opens and configures an SQLite database connection."""
    target = Path(db_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Initializes tables, FTS5 virtual index, triggers, and indices."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT,
                total_steps INTEGER DEFAULT 0,
                file_path TEXT,
                last_indexed_mtime REAL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                created_at TEXT,
                role TEXT,
                type TEXT,
                content TEXT,
                tool_names TEXT,
                FOREIGN KEY(conversation_id)
                    REFERENCES conversations(conversation_id)
                    ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conv_step
            ON messages(conversation_id, step_index);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                title,
                tool_names,
                tokenize='porter unicode61'
            );
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, title, tool_names)
                VALUES (
                    new.id,
                    new.content,
                    (
                        SELECT title FROM conversations
                        WHERE conversation_id = new.conversation_id
                    ),
                    new.tool_names
                );
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.id;
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                DELETE FROM messages_fts WHERE rowid = old.id;
                INSERT INTO messages_fts(rowid, content, title, tool_names)
                VALUES (
                    new.id,
                    new.content,
                    (
                        SELECT title FROM conversations
                        WHERE conversation_id = new.conversation_id
                    ),
                    new.tool_names
                );
            END;
            """
        )


def sanitize_fts_query(query: str) -> str:
    """Sanitizes user input into a valid SQLite FTS5 query expression."""
    cleaned = re.sub(r"[^\w\s]", " ", query)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    # Format each token as prefix query or exact term
    return " ".join(f'"{t}"*' for t in tokens)


def search_messages(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Searches indexed messages and conversations using FTS5."""
    clean_query = sanitize_fts_query(query)
    if not clean_query:
        return []

    sql = """
        SELECT
            m.id,
            m.conversation_id,
            m.step_index,
            m.role,
            m.type,
            m.content,
            m.tool_names,
            c.title,
            c.updated_at,
            snippet(messages_fts, 0, '<b>', '</b>', '...', 16) AS snippet,
            bm25(messages_fts) AS rank
        FROM messages_fts f
        JOIN messages m ON f.rowid = m.id
        JOIN conversations c ON m.conversation_id = c.conversation_id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    try:
        cursor = conn.execute(sql, (clean_query, limit))
        return [
            {
                "message_id": row["id"],
                "conversation_id": row["conversation_id"],
                "step_index": row["step_index"],
                "role": row["role"],
                "type": row["type"],
                "content": row["content"],
                "tool_names": row["tool_names"],
                "title": row["title"],
                "updated_at": row["updated_at"],
                "snippet": row["snippet"],
                "rank": row["rank"],
            }
            for row in cursor.fetchall()
        ]
    except sqlite3.OperationalError:
        return []
