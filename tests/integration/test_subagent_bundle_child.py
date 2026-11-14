"""End-to-end: a subagent turn runs on a bundle-built child context.

The child context is built by the bundle loader, not by direct service
construction; the turn runs through the real agent loop against a mock
provider, and the child session persists under the subsessions dir.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from anima import Context
from magitech_harness import check_bundle_entries, create_harness
from magitech_harness.llm.service import MockLLMProvider
from magitech_harness.tools.definition import Tool

from mth_plugins.tools.subagent.manager import SubagentManager
from mth_plugins.tools.subagent.types import SubagentSpec, SubagentState


@pytest.mark.asyncio
async def test_subagent_turn_on_bundle_child_persists(tmp_path: Path) -> None:
    parent_ctx = create_harness(storage_dir=tmp_path / "parent")
    await parent_ctx.flush()
    check_bundle_entries(parent_ctx)

    mock_provider = MockLLMProvider()
    parent_ctx.llm.register_provider("mock", mock_provider)
    parent_ctx.llm.set_active_provider("mock")
    parent_ctx.tools.register(
        Tool(name="read_file", description="", parameters={}, handler=AsyncMock())
    )
    parent_ctx.tools.register(
        Tool(name="write_file", description="", parameters={}, handler=AsyncMock())
    )
    parent_ctx.tools.register(
        Tool(name="invoke_subagent", description="", parameters={}, handler=AsyncMock())
    )

    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    captured: list[Context] = []

    def _recording_create_harness(
        storage_dir: Path | str | None = None, **kwargs: object
    ) -> Context:
        ctx = create_harness(storage_dir=storage_dir)
        captured.append(ctx)
        return ctx

    with patch(
        "mth_plugins.tools.subagent.manager.create_harness",
        side_effect=_recording_create_harness,
    ):
        recs = await manager.invoke(
            [
                SubagentSpec(
                    role="worker",
                    prompt="Say hello",
                    allowed_tools=frozenset({"read_file"}),
                    wait=True,
                )
            ]
        )

    assert len(recs) == 1
    rec = recs[0]
    assert rec.state == SubagentState.COMPLETED
    assert rec.summary == "Default mock response"
    assert rec.effective_tools == ["read_file"]

    assert len(captured) == 1
    child_ctx = captured[0]

    # Providers copied through the public seams; active provider preserved.
    assert set(child_ctx.llm.providers) == {"mock"}
    assert child_ctx.llm.active_provider is mock_provider

    # Tools filtered through the public seams.
    assert child_ctx.tools.get("read_file") is not None
    assert child_ctx.tools.get("write_file") is None
    assert child_ctx.tools.get("invoke_subagent") is None

    # The bundle-built child carries rows the old child never had.
    assert hasattr(child_ctx, "sessionTitle")
    assert hasattr(child_ctx, "sessionProjections")
    assert hasattr(child_ctx, "sessionProjectionCache")

    # The child session persists under the subsessions dir.
    await child_ctx.sessions.flush()
    assert rec.session_path.exists()
    assert tmp_path / "subsessions" in rec.session_path.parents
