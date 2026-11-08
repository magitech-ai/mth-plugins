"""Integration test between magitech-harness and mth-plugins."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from magitech_harness import create_harness

from mth_plugins.index import REPO_ROOT, scan_plugins
from mth_plugins.providers.openrouter.provider import OpenRouterProvider


@pytest.mark.asyncio
async def test_end_to_end_marketplace_turn(tmp_path: Path) -> None:
    """Verifies complete end-to-end turn using marketplace plugins."""
    # 1. Initialize Harness
    ctx = create_harness(storage_dir=tmp_path / "sessions")
    await ctx.flush()

    # 2. Discover plugins from marketplace repo root
    artifacts = scan_plugins(REPO_ROOT)
    artifact_map = {a.name: a for a in artifacts}
    assert "openrouter-provider" in artifact_map
    assert "bash-tool" in artifact_map
    assert "fs-tool" in artifact_map
    assert "truncation-guard" in artifact_map

    # 3. Mount tools and guardrail from marketplace
    ctx.plugins.mount_plugin(artifact_map["bash-tool"].manifest)
    ctx.plugins.mount_plugin(artifact_map["fs-tool"].manifest)
    ctx.plugins.mount_plugin(
        artifact_map["truncation-guard"].manifest,
        max_lines=3,
        max_bytes=100,
    )

    # 4. Mount OpenRouter provider with mocked httpx client
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # Turn 1: Model requests bash tool call
    resp1_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Let me run that command for you.",
                    "tool_calls": [
                        {
                            "id": "call-bash-1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps(
                                    {"command": "echo 'Hello from Magitech!'"}
                                ),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    # Turn 2: Model finishes with answer
    resp2_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "The command executed successfully and printed: "
                        "Hello from Magitech!"
                    ),
                },
                "finish_reason": "stop",
            }
        ]
    }

    mock_resp1 = AsyncMock(spec=httpx.Response)
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = resp1_data

    mock_resp2 = AsyncMock(spec=httpx.Response)
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = resp2_data

    mock_client.post.side_effect = [mock_resp1, mock_resp2]

    provider = OpenRouterProvider(api_key="mock-key", client=mock_client)
    ctx.llm.register_provider("openrouter", provider)
    await ctx.flush()

    assert ctx.tools.get("bash") is not None
    assert ctx.tools.get("read_file") is not None
    assert ctx.tools.get("write_file") is not None
    assert ctx.tools.get("edit_file") is not None
    assert "openrouter" in ctx.llm.providers

    # 5. Run turn via agent loop with OpenRouter model slug
    session = ctx.sessions.create()
    result = await ctx.agent_loop.run_turn(
        session,
        "Run an echo command.",
        model="openrouter/openai/gpt-4o",
    )

    assert "The command executed successfully" in result
    # user -> model (tool_call) -> tool_result -> model (final)
    assert len(session.events) >= 4
