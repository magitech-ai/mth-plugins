"""Integration test between magitech-harness and mth-plugins."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from magitech_harness import create_harness
from magitech_harness.session.events import EventType

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
    assert "pollinations-provider" in artifact_map
    assert "bash-tool" in artifact_map
    assert "fs-tool" in artifact_map
    assert "truncation-guard" in artifact_map
    assert "compaction-guard" in artifact_map

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


@pytest.mark.asyncio
async def test_end_to_end_marketplace_streaming_and_compaction(
    tmp_path: Path,
) -> None:
    """Verifies streaming agent turn with tool calling and context compaction."""
    ctx = create_harness(storage_dir=tmp_path / "sessions")
    await ctx.flush()

    artifacts = scan_plugins(REPO_ROOT)
    artifact_map = {a.name: a for a in artifacts}

    ctx.plugins.mount_plugin(artifact_map["bash-tool"].manifest)
    ctx.plugins.mount_plugin(artifact_map["compaction-guard"].manifest)

    # Mock SSE stream responses
    tool_args = json.dumps({"command": "echo 'Stream test'"})
    tc_chunk = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "id": "call-stream-1",
                            "function": {
                                "name": "bash",
                                "arguments": tool_args,
                            },
                        }
                    ]
                }
            }
        ]
    }
    tc_done = {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}

    answer_chunk = {"choices": [{"delta": {"content": "Stream completed."}}]}
    answer_done = {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    step1_lines = [
        f"data: {json.dumps(tc_chunk)}",
        f"data: {json.dumps(tc_done)}",
        "data: [DONE]",
    ]
    step2_lines = [
        f"data: {json.dumps(answer_chunk)}",
        f"data: {json.dumps(answer_done)}",
        "data: [DONE]",
    ]

    class MockStreamResp:
        def __init__(self, sse_lines):
            self.status_code = 200
            self._lines = sse_lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            for line in self._lines:
                yield line

    step_counter = 0

    class MockStreamClient:
        def stream(self, method, url, **kwargs):
            nonlocal step_counter
            step_counter += 1
            if step_counter == 1:
                return MockStreamResp(step1_lines)
            return MockStreamResp(step2_lines)

    provider = OpenRouterProvider(api_key="mock-key", client=MockStreamClient())
    ctx.llm.register_provider("openrouter", provider)
    await ctx.flush()

    session = ctx.sessions.create("sess_stream_e2e")
    streamed_events = [
        ev
        async for ev in ctx.agent_loop.stream_turn(
            session,
            "Run streaming echo",
            model="openrouter/gpt-4o",
        )
    ]

    assert len(streamed_events) > 0
    token_events = [e for e in streamed_events if e.get("type") == "chunk"]
    assert len(token_events) > 0
    assert token_events[0]["text"] == "Stream completed."

    # Turn complete: history has user, tool call, tool result, assistant
    assert len(session.events) >= 4

    # Trigger context compaction through waterfall
    compact_res = await ctx.waterfall(
        "session/compact",
        {"session": session, "status": "requested"},
        default_handler=lambda p: p,
    )

    assert compact_res["compacted"] is True
    assert "summary" in compact_res
    assert session.events[-1].type == EventType.COMPACTION

    # Verify message projection folds history
    msgs = session.derive_messages()
    assert len(msgs) >= 2
    assert "[Conversation summary up to checkpoint]:" in msgs[0]["content"]


@pytest.mark.asyncio
async def test_end_to_end_pollinations_anonymous_turn(tmp_path: Path) -> None:
    """Verifies end-to-end turn using anonymous Pollinations provider."""
    ctx = create_harness(storage_dir=tmp_path / "sessions")
    await ctx.flush()

    artifacts = scan_plugins(REPO_ROOT)
    artifact_map = {a.name: a for a in artifacts}

    # Mount provider directly from marketplace artifact
    ctx.plugins.mount_plugin(artifact_map["pollinations-provider"].manifest)
    await ctx.flush()

    captured_headers: dict = {}
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers, captured_payload
        captured_headers = dict(request.headers)
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Free anonymous turn success!",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    # Inject mock client into registered provider
    provider = ctx.llm.get_provider("pollinations")
    assert provider is not None
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    session = ctx.sessions.create("sess_pollinations_e2e")
    result = await ctx.agent_loop.run_turn(
        session,
        "Hello anonymous assistant",
        model="pollinations/openai",
    )

    assert result == "Free anonymous turn success!"
    assert captured_payload["model"] == "openai"
    assert "authorization" not in captured_headers
    assert "Authorization" not in captured_headers
