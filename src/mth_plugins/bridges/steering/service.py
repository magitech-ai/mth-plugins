"""SteeringBridgeService: Resolves layered steering docs into system prompt."""

from __future__ import annotations

import logging
from pathlib import Path

from anima import Context, Disposer, Service

from mth_plugins.bridges.steering.collector import (
    collect_steering_documents,
    format_hierarchical_steering,
)

logger = logging.getLogger("mth_plugins.bridges.steering")


class SteeringBridgeService(Service):
    """Service managing discovery and prompt mounting of hierarchical steering docs."""

    def __init__(
        self,
        ctx: Context,
        project_path: Path | str | None = None,
        agent_name: str | None = None,
    ) -> None:
        super().__init__(ctx, "steering")
        self.project_path = project_path
        self.agent_name = agent_name
        self._prompt_disposer: Disposer | None = None

        def _cleanup() -> None:
            if self._prompt_disposer is not None:
                self._prompt_disposer()
                self._prompt_disposer = None

        self.ctx.effect(lambda: _cleanup)

    def refresh_steering(
        self,
        project_path: Path | str | None = None,
        agent_name: str | None = None,
    ) -> str:
        """Collects steering guidelines across layers and updates ctx.system_prompt."""
        if project_path is not None:
            self.project_path = project_path
        if agent_name is not None:
            self.agent_name = agent_name

        if self.ctx.has("layers"):
            layers = self.ctx.layers.get_layers(
                project_path=self.project_path, agent_name=self.agent_name
            )
            docs = collect_steering_documents(layers)
        else:
            docs = []

        formatted = format_hierarchical_steering(docs)

        if self._prompt_disposer is not None:
            self._prompt_disposer()
            self._prompt_disposer = None

        if formatted and self.ctx.has("system_prompt"):
            self._prompt_disposer = self.ctx.system_prompt.register_section(
                "steering_guidelines", formatted
            )

        return formatted
