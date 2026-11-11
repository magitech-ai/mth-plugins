"""WorkspaceTrustGate service: Evaluates project workspace trust policies."""

from __future__ import annotations

import logging
from pathlib import Path

from anima import Context, Service

from mth_plugins.guards.trust.hasher import compute_directory_tree_hash
from mth_plugins.guards.trust.store import TrustDecision, TrustStore

logger = logging.getLogger("mth_plugins.guards.trust")


class WorkspaceTrustGate(Service):
    """Guards workspace extension execution behind cryptographic trust checks."""

    def __init__(self, ctx: Context, config: dict | None = None) -> None:
        super().__init__(ctx, "trust")
        cfg = config or {}
        store: TrustStore | None = cfg.get("store")
        store_path: Path | str | None = cfg.get("store_path")
        path = Path(store_path) if store_path else None
        self.store = store or TrustStore(path)

    async def check_project_trust(
        self,
        project_path: Path | str,
        prompt_user: bool = True,
    ) -> bool:
        """Verifies whether a project workspace is trusted.

        Args:
            project_path: Path to the root of the project.
            prompt_user: If True and decision is unspecified, requests approval.

        Returns:
            True if workspace is trusted, False otherwise.
        """
        proj_dir = Path(project_path).resolve()
        agents_dir = proj_dir / ".agents"

        # Safe default: if project defines no .agents extension layer, it is safe
        if not agents_dir.is_dir():
            return True

        current_hash = compute_directory_tree_hash(agents_dir)
        decision = self.store.get_decision(proj_dir, current_hash)

        if decision in (TrustDecision.TRUST_EXACT, TrustDecision.TRUST_PARENT):
            return True

        if decision == TrustDecision.DECLINE:
            logger.info("Project %s is explicitly declined.", proj_dir)
            return False

        # Decision is UNSPECIFIED
        if prompt_user and self.ctx.has("approvals"):
            logger.info("Prompting user for workspace trust verdict on %s", proj_dir)
            verdict = await self.ctx.approvals.request_approval(
                tool_name="workspace_trust",
                arguments={"project": str(proj_dir), "tree_hash": current_hash},
                description=f"Trust workspace configuration for '{proj_dir.name}'?",
            )
            if verdict:
                self.store.set_decision(
                    proj_dir, TrustDecision.TRUST_EXACT, current_hash
                )
                return True

            self.store.set_decision(proj_dir, TrustDecision.DECLINE, current_hash)
            return False

        # Non-interactive or no approvals broker mounted: fail closed
        logger.warning(
            "Untrusted workspace %s declined under fail-closed policy.",
            proj_dir,
        )
        return False
