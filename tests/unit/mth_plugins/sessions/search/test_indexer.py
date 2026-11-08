"""Unit tests for incremental SessionIndexer parsing and storage."""

import json
import time
from pathlib import Path

from mth_plugins.sessions.search.db import search_messages
from mth_plugins.sessions.search.indexer import SessionIndexer


def test_indexer_index_directory_and_incremental(tmp_path: Path) -> None:
    db_file = tmp_path / "search.db"
    indexer = SessionIndexer(db_file)

    # 1. Non-existent directory returns 0
    assert indexer.index_directory(tmp_path / "nonexistent") == 0

    # 2. Directory with session logs
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    sess1_file = logs_dir / "sess-1.jsonl"
    events1 = [
        {
            "seq": 1,
            "type": "turn/start",
            "timestamp": "2026-11-08T01:00:00Z",
            "payload": {"title": "Debug Memory Leak"},
        },
        {
            "seq": 2,
            "type": "user/message",
            "timestamp": "2026-11-08T01:00:05Z",
            "payload": {"text": "Why is the process consuming 2GB RAM?"},
        },
        {
            "seq": 3,
            "type": "assistant/message",
            "timestamp": "2026-11-08T01:00:10Z",
            "payload": {
                "text": "Checking active allocations.",
                "tool_calls": [{"name": "read_file", "arguments": {"path": "main.py"}}],
            },
        },
        {
            "seq": 4,
            "type": "tools/result",
            "timestamp": "2026-11-08T01:00:12Z",
            "payload": {
                "name": "read_file",
                "content": (
                    "global_cache = []\ndef append(): global_cache.append(b'x'*1000)"
                ),
            },
        },
    ]
    sess1_file.write_text(
        "\n".join(json.dumps(e) for e in events1) + "\n", encoding="utf-8"
    )

    indexed = indexer.index_directory(logs_dir)
    assert indexed == 1

    # Search for term from sess-1
    hits = search_messages(indexer._conn, "consuming 2GB")
    assert len(hits) == 1
    assert hits[0]["conversation_id"] == "sess-1"
    assert hits[0]["title"] == "Debug Memory Leak"

    # 3. Second run with unchanged file: returns 0 (not modified)
    assert indexer.index_directory(logs_dir) == 0

    # 4. Modify file with newer mtime
    time.sleep(0.01)
    events1.extend(
        [
            {
                "seq": 5,
                "type": "assistant/message",
                "timestamp": "2026-11-08T01:00:15Z",
                "payload": {
                    "text": "Found unbound global cache in main.py.",
                    "tool_calls": "not-a-list",
                },
            },
            {
                "seq": 6,
                "type": "assistant/message",
                "payload": {
                    "text": "Check again",
                    "tool_calls": ["string-call", {"missing_name": 1}],
                },
            },
            {
                "seq": 7,
                "type": "tools/result",
                "payload": {"content": "result without tool name"},
            },
            {
                "seq": 8,
                "type": "custom/event",
                "payload": "not-a-dict",
            },
        ]
    )
    sess1_file.write_text(
        "\n".join(json.dumps(e) for e in events1) + "\n", encoding="utf-8"
    )
    # Touch mtime to ensure greater than previous
    Path(sess1_file).touch()
    assert indexer.index_file(sess1_file) is True

    hits_updated = search_messages(indexer._conn, "unbound global cache")
    assert len(hits_updated) == 1

    indexer.close()


def test_indexer_file_edge_cases(tmp_path: Path) -> None:
    db_file = tmp_path / "search.db"
    indexer = SessionIndexer(db_file)

    # 1. Nonexistent file returns False
    assert indexer.index_file(tmp_path / "missing.jsonl") is False

    # 2. Corrupted JSON file returns False
    bad_file = tmp_path / "corrupted.jsonl"
    bad_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
    assert indexer.index_file(bad_file) is False

    # 3. Empty file returns False
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("\n\n   \n", encoding="utf-8")
    assert indexer.index_file(empty_file) is False

    indexer.close()
