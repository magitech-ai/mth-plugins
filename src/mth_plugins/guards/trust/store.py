"""Persistent store for workspace trust decisions and integrity records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class TrustDecision(StrEnum):
    """Possible trust verdict states for a workspace."""

    TRUST_EXACT = "trust_exact"
    TRUST_PARENT = "trust_parent"
    DECLINE = "decline"
    UNSPECIFIED = "unspecified"


DEFAULT_TRUST_FILE = Path.home() / ".agents" / "approval" / "trust.json"


class TrustStore:
    """Manages persistent trust records with atomic writes."""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path or DEFAULT_TRUST_FILE

    def _read_data(self) -> dict[str, Any]:
        if not self.file_path.is_file():
            return {"projects": {}, "trusted_parents": []}
        try:
            content = self.file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                return {"projects": {}, "trusted_parents": []}
            return data
        except Exception:
            return {"projects": {}, "trusted_parents": []}

    def _write_data(self, data: dict[str, Any]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.file_path.with_suffix(".tmp")
        content = json.dumps(data, indent=2, sort_keys=True)
        tmp_file.write_text(content, encoding="utf-8")
        tmp_file.replace(self.file_path)

    def get_decision(self, project_path: Path, current_tree_hash: str) -> TrustDecision:
        """Determines the trust decision for a project based on stored policies."""
        resolved = project_path.resolve()
        data = self._read_data()

        # 1. Check if project is enclosed in a trusted parent directory
        trusted_parents = data.get("trusted_parents", [])
        for parent_str in trusted_parents:
            parent_path = Path(parent_str).resolve()
            if resolved.is_relative_to(parent_path):
                return TrustDecision.TRUST_PARENT

        # 2. Check exact project record
        projects = data.get("projects", {})
        proj_key = str(resolved)
        record = projects.get(proj_key)

        if not record or not isinstance(record, dict):
            return TrustDecision.UNSPECIFIED

        decision_str = record.get("decision")
        if decision_str == TrustDecision.DECLINE:
            return TrustDecision.DECLINE

        if decision_str == TrustDecision.TRUST_EXACT:
            stored_hash = record.get("tree_hash")
            if stored_hash == current_tree_hash:
                return TrustDecision.TRUST_EXACT
            # Tree hash mutated: requires re-verification
            return TrustDecision.UNSPECIFIED

        return TrustDecision.UNSPECIFIED

    def set_decision(
        self,
        project_path: Path,
        decision: TrustDecision,
        tree_hash: str | None = None,
    ) -> None:
        """Records an explicit trust decision for a project path."""
        resolved = project_path.resolve()
        data = self._read_data()
        projects = data.setdefault("projects", {})

        projects[str(resolved)] = {
            "decision": decision.value,
            "tree_hash": tree_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._write_data(data)

    def add_trusted_parent(self, parent_path: Path) -> None:
        """Whitelists an entire parent directory as trusted."""
        resolved = str(parent_path.resolve())
        data = self._read_data()
        parents = data.setdefault("trusted_parents", [])
        if resolved not in parents:
            parents.append(resolved)
            self._write_data(data)

    def clear(self) -> None:
        """Clears all stored trust decisions."""
        self._write_data({"projects": {}, "trusted_parents": []})
