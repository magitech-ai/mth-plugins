"""SessionSearchService providing high-level indexing and search capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from anima import Context, Service

from mth_plugins.sessions.search.db import search_messages
from mth_plugins.sessions.search.indexer import SessionIndexer


class SessionSearchService(Service):
    """Service providing SQLite FTS5 search across indexed session event logs."""

    inject: ClassVar[list[str]] = ["sessions"]

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(ctx, "session_search")
        db_path = (config or {}).get("db_path")
        path = (
            Path(db_path)
            if db_path is not None
            else (Path.home() / ".agents" / "session_search.db")
        )
        self.indexer = SessionIndexer(path)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Executes full-text query across indexed conversations and messages."""
        return search_messages(self.indexer._conn, query, limit=limit)

    def index_sessions(self, target_dir: Path | None = None) -> int:
        """Indexes all session logs in target directory or configured session store."""
        search_dir = target_dir
        if search_dir is None:
            sessions_svc = getattr(self.ctx, "sessions", None)
            search_dir = getattr(sessions_svc, "base_storage_dir", None)

        if search_dir is not None and Path(search_dir).is_dir():
            return self.indexer.index_directory(Path(search_dir))
        return 0

    def close(self) -> None:
        """Closes the underlying database connection."""
        self.indexer.close()
