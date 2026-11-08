"""Incremental JSONL session indexer for SQLite FTS5."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mth_plugins.sessions.search.db import get_db_connection, init_db

logger = logging.getLogger(__name__)


def _parse_event_message(
    ev_type: str, payload: dict[str, Any]
) -> tuple[str | None, str, list[str]]:
    """Extracts role, content, and tool names from an event payload."""
    if ev_type == "user/message":
        return "user", str(payload.get("text", "")), []
    if ev_type == "assistant/message":
        calls = payload.get("tool_calls", [])
        tool_names = (
            [
                str(call["name"])
                for call in calls
                if isinstance(call, dict) and "name" in call
            ]
            if isinstance(calls, list)
            else []
        )
        return "assistant", str(payload.get("text", "")), tool_names
    if ev_type == "tools/result":
        tool_names = [str(payload["name"])] if "name" in payload else []
        return "tool", str(payload.get("content", "")), tool_names
    return None, "", []


class SessionIndexer:
    """Parses durable session event logs and updates SQLite full-text search index."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn = get_db_connection(self.db_path)
        init_db(self._conn)

    def close(self) -> None:
        """Closes the underlying database connection."""
        self._conn.close()

    def index_directory(self, dir_path: Path) -> int:
        """Scans a directory for *.jsonl files and updates modified sessions."""
        if not dir_path.is_dir():
            return 0

        indexed_count = 0
        for jsonl_file in dir_path.glob("*.jsonl"):
            if self.index_file(jsonl_file):
                indexed_count += 1
        return indexed_count

    def index_file(self, file_path: Path) -> bool:
        """Indexes a single session JSONL file if modified since last index."""
        if not file_path.is_file():
            return False

        mtime = file_path.stat().st_mtime
        conversation_id = file_path.stem

        cursor = self._conn.execute(
            "SELECT last_indexed_mtime FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = cursor.fetchone()
        if (
            row is not None
            and row["last_indexed_mtime"] is not None
            and mtime <= row["last_indexed_mtime"]
        ):
            return False

        try:
            events = self._parse_jsonl(file_path)
        except (OSError, json.JSONDecodeError) as ex:
            logger.warning("Failed to parse session log %s: %s", file_path, ex)
            return False

        if not events:
            return False

        self._store_session_events(conversation_id, file_path, mtime, events)
        return True

    def _parse_jsonl(self, file_path: Path) -> list[dict[str, Any]]:
        """Reads and parses line-delimited JSON objects from session file."""
        events: list[dict[str, Any]] = []
        with file_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    events.append(json.loads(stripped))
        return events

    def _store_session_events(
        self,
        conversation_id: str,
        file_path: Path,
        mtime: float,
        events: list[dict[str, Any]],
    ) -> None:
        """Writes parsed events into conversations and messages tables."""
        created_at: str | None = None
        updated_at: str | None = None
        title: str | None = None
        parsed_messages: list[dict[str, Any]] = []

        step_counter = 0
        for ev in events:
            ts = ev.get("timestamp") or ev.get("created_at")
            if created_at is None and ts:
                created_at = str(ts)
            if ts:
                updated_at = str(ts)

            ev_type = str(ev.get("type", "unknown"))
            payload = ev.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            # Check if event contains a session title
            if "title" in payload:
                title = str(payload["title"])

            role, content, tool_names = _parse_event_message(ev_type, payload)

            if role is not None and (content or tool_names):
                step_counter += 1
                parsed_messages.append(
                    {
                        "step_index": step_counter,
                        "created_at": ts,
                        "role": role,
                        "type": ev_type,
                        "content": content,
                        "tool_names": ",".join(tool_names) if tool_names else None,
                    }
                )

        with self._conn:
            # Delete old messages to avoid duplicates
            self._conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            # Insert or replace conversation metadata
            self._conn.execute(
                """
                INSERT INTO conversations (
                    conversation_id, title, created_at, updated_at,
                    total_steps, file_path, last_indexed_mtime
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    title = coalesce(excluded.title, conversations.title),
                    updated_at = excluded.updated_at,
                    total_steps = excluded.total_steps,
                    file_path = excluded.file_path,
                    last_indexed_mtime = excluded.last_indexed_mtime
                """,
                (
                    conversation_id,
                    title,
                    created_at,
                    updated_at,
                    step_counter,
                    str(file_path),
                    mtime,
                ),
            )
            # Insert message rows
            for msg in parsed_messages:
                self._conn.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, step_index, created_at,
                        role, type, content, tool_names
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        msg["step_index"],
                        msg["created_at"],
                        msg["role"],
                        msg["type"],
                        msg["content"],
                        msg["tool_names"],
                    ),
                )
