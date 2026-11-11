"""Unit tests for SessionSearchService."""

import json
from pathlib import Path

from anima import Context
from magitech_harness.session.service import SessionService

from mth_plugins.sessions.search.service import SessionSearchService


def test_session_search_service(tmp_path: Path) -> None:
    ctx = Context()
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    SessionService(ctx, {"base_storage_dir": sessions_dir})

    db_path = tmp_path / "search.db"
    service = SessionSearchService(ctx, {"db_path": db_path})

    # 1. Initially empty
    assert service.search("anything") == []

    # 2. Add a session file
    s_file = sessions_dir / "s-1.jsonl"
    s_file.write_text(
        json.dumps(
            {
                "seq": 1,
                "type": "user/message",
                "timestamp": "2026-11-08T00:00:00Z",
                "payload": {"text": "Authentication JWT validation failure"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Index using context sessions directory
    indexed = service.index_sessions()
    assert indexed == 1

    # Search matches
    results = service.search("JWT validation")
    assert len(results) == 1
    assert results[0]["conversation_id"] == "s-1"

    # Index explicit target_dir
    assert service.index_sessions(sessions_dir) == 0

    # Index when no directory available
    empty_ctx = Context()
    empty_svc = SessionSearchService(empty_ctx, {"db_path": tmp_path / "empty.db"})
    assert empty_svc.index_sessions() == 0
    empty_svc.close()

    service.close()
