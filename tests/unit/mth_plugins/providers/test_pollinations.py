"""Unit tests for Pollinations free anonymous provider and component."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from anima import Context
from magitech_harness.agent.cancellation import AbortError, AbortSignal
from magitech_harness.llm.service import LLMService
from magitech_harness.llm.types import ModelChunk

from mth_plugins.providers.pollinations.component import apply
from mth_plugins.providers.pollinations.provider import (
    PollinationsProvider,
    wire_model_id,
)


def test_wire_model_id() -> None:
    """Verifies reducing model slug to wire id."""
    assert wire_model_id("pollinations/openai") == "openai"
    assert wire_model_id("pollinations/openai-fast") == "openai-fast"
    assert wire_model_id("openai") == "openai"
    assert wire_model_id("custom-model") == "custom-model"


@pytest.mark.asyncio
async def test_pollinations_provider_keyless_request_sends_no_auth_header() -> None:
    """Verifies that an unkeyed request does NOT send Authorization header."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from Pollinations!",
                },
                "finish_reason": "stop",
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=mock_client)
    res = await provider.generate(
        messages=[{"role": "user", "content": "Hi"}],
        system_prompt="You are a helpful assistant.",
        model="pollinations/openai",
        temperature=0.7,
        max_tokens=100,
        top_p=0.9,
    )

    assert res.text == "Hello from Pollinations!"
    assert res.finish_reason == "stop"
    assert res.tool_calls == []

    call_args = mock_client.post.call_args
    assert call_args is not None
    headers = call_args.kwargs["headers"]
    assert "Authorization" not in headers
    assert "authorization" not in headers

    payload = call_args.kwargs["json"]
    assert payload["model"] == "openai"
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 100
    assert payload["top_p"] == 0.9
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_pollinations_provider_keyed_request_sends_bearer_header() -> None:
    """Verifies that a keyed request sends Authorization: Bearer <key>."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Keyed response"}}]
    }
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(api_key="secret-token", client=mock_client)
    res = await provider.generate(messages=[{"role": "user", "content": "Hi"}])
    assert res.text == "Keyed response"

    headers = mock_client.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_pollinations_provider_generate_with_existing_system_message() -> None:
    """Verifies that system prompt is not duplicated if already present in messages."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "OK"}}]
    }
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=mock_client)
    res = await provider.generate(
        messages=[
            {"role": "system", "content": "Existing system prompt"},
            {"role": "user", "content": "Task"},
        ],
        system_prompt="New prompt",
    )
    assert res.text == "OK"
    payload = mock_client.post.call_args.kwargs["json"]
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["content"] == "Existing system prompt"


@pytest.mark.asyncio
async def test_pollinations_provider_generate_tool_calls() -> None:
    """Verifies parsing tool calls from Pollinations model response."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Calling tools",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "uptime"}',
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "bad_tool",
                                "arguments": "{invalid-json",
                            },
                        },
                        {
                            "id": "call_3",
                            "type": "function",
                            "function": {
                                "name": "dict_tool",
                                "arguments": {"already": "parsed"},
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=mock_client)
    res = await provider.generate(
        messages=[{"role": "user", "content": "check system"}],
        tools=[{"type": "function", "function": {"name": "bash"}}],
    )

    assert len(res.tool_calls) == 3
    assert res.tool_calls[0].call_id == "call_1"
    assert res.tool_calls[0].name == "bash"
    assert res.tool_calls[0].arguments == {"command": "uptime"}
    assert res.tool_calls[1].arguments == {"raw": "{invalid-json"}
    assert res.tool_calls[2].arguments == {"already": "parsed"}


@pytest.mark.asyncio
async def test_pollinations_provider_generate_empty_choices() -> None:
    """Verifies handling when choices list is empty."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=mock_client)
    res = await provider.generate(messages=[{"role": "user", "content": "Hi"}])
    assert res.text == ""
    assert res.finish_reason == "stop"


@pytest.mark.asyncio
async def test_pollinations_provider_generate_error() -> None:
    """Verifies error handling on non-200 status codes."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.text = "Too Many Requests"
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=mock_client)
    with pytest.raises(
        RuntimeError, match="Pollinations API error 429: Too Many Requests"
    ):
        await provider.generate(messages=[{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_pollinations_provider_default_client_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that an internally created client is closed after generate."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_client.post.return_value = mock_resp

    provider = PollinationsProvider(client=None)
    monkeypatch.setattr(provider, "_get_client", lambda: mock_client)

    await provider.generate(messages=[{"role": "user", "content": "Hi"}])
    mock_client.aclose.assert_awaited_once()


def test_pollinations_provider_default_get_client() -> None:
    """Verifies _get_client returns httpx.AsyncClient if client is None."""
    provider = PollinationsProvider()
    client = provider._get_client()
    assert isinstance(client, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_pollinations_provider_stream_chunks() -> None:
    """Verifies streaming token deltas, tool calls, and reasoning deltas from SSE."""
    tc_stream = {
        "id": "c_stream",
        "function": {"name": "bash", "arguments": json.dumps({"command": "pwd"})},
    }
    tc_bad = {
        "id": "c_bad",
        "function": {"name": "invalid", "arguments": "{not-json"},
    }
    tc_dict = {
        "id": "c_dict",
        "function": {"name": "dict", "arguments": {"k": "v"}},
    }
    chunk_tools = json.dumps(
        {"choices": [{"delta": {"tool_calls": [tc_stream, tc_bad, tc_dict]}}]}
    )
    chunk_reasoning = json.dumps(
        {"choices": [{"delta": {"reasoning": "thinking step"}}]}
    )
    chunk_world = json.dumps(
        {"choices": [{"delta": {"content": "World!"}, "finish_reason": "stop"}]}
    )
    lines = [
        "",
        ": keepalive comment",
        "data:",
        "data: {invalid json",
        'data: {"choices": []}',
        'data: {"choices": [{"delta": {}}]}',
        'data: {"choices": [{"delta": {"content": "Hello "}}]}',
        f"data: {chunk_reasoning}",
        f"data: {chunk_tools}",
        f"data: {chunk_world}",
        "data: [DONE]",
    ]

    captured_kwargs: dict = {}

    class MockStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            for line in lines:
                yield line

    class MockClient:
        def stream(self, method, url, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return MockStreamResponse()

    provider = PollinationsProvider(client=MockClient())
    chunks: list[ModelChunk] = [
        c
        async for c in provider.stream(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="sys prompt",
            model="pollinations/openai",
            tools=[{"type": "function", "function": {"name": "bash"}}],
            temperature=0.3,
            max_tokens=80,
            top_p=0.95,
        )
    ]

    assert len(chunks) == 3
    assert chunks[0].text == "Hello "
    assert len(chunks[1].tool_calls) == 3
    assert chunks[1].tool_calls[0].name == "bash"
    assert chunks[1].tool_calls[0].arguments == {"command": "pwd"}
    assert chunks[1].tool_calls[1].arguments == {"raw": "{not-json"}
    assert chunks[1].tool_calls[2].arguments == {"k": "v"}
    assert chunks[2].text == "World!"
    assert chunks[2].finish_reason == "stop"

    payload = captured_kwargs["json"]
    assert payload["model"] == "openai"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 80
    assert payload["top_p"] == 0.95
    assert payload["tools"] == [{"type": "function", "function": {"name": "bash"}}]
    assert payload["messages"][0]["role"] == "system"

    # Verify keyless request sends no authorization header
    headers = captured_kwargs["headers"]
    assert "Authorization" not in headers

    # Test abort signal before start
    signal = AbortSignal()
    signal.abort()
    with pytest.raises(AbortError, match="Operation was aborted"):
        async for _ in provider.stream(messages=[], signal=signal):
            pass


@pytest.mark.asyncio
async def test_pollinations_provider_stream_mid_stream_abort() -> None:
    """Verifies mid-stream cancellation when AbortSignal triggers."""
    signal = AbortSignal()

    class MockStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "First"}}]}'
            signal.abort()
            yield 'data: {"choices": [{"delta": {"content": "Second"}}]}'

    class MockClient:
        def stream(self, method, url, **kwargs):
            return MockStreamResponse()

    provider = PollinationsProvider(client=MockClient())
    with pytest.raises(AbortError, match="Operation was aborted"):
        async for _ in provider.stream(
            messages=[{"role": "user", "content": "hi"}], signal=signal
        ):
            pass


@pytest.mark.asyncio
async def test_pollinations_provider_stream_default_client_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that an internally created client is closed after stream."""
    client_closed = False

    class MockInternalClient:
        def stream(self, method, url, **kwargs):
            class Response:
                status_code = 200

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def aiter_lines(self):
                    yield 'data: {"choices": [{"delta": {"content": "Done"}}]}'

            return Response()

        async def aclose(self):
            nonlocal client_closed
            client_closed = True

    provider = PollinationsProvider(client=None)
    monkeypatch.setattr(provider, "_get_client", MockInternalClient)

    async for _ in provider.stream(messages=[{"role": "user", "content": "hi"}]):
        pass

    assert client_closed is True


@pytest.mark.asyncio
async def test_pollinations_provider_stream_error() -> None:
    """Verifies streaming handles non-200 HTTP status code."""

    class MockErrorStreamResponse:
        status_code = 502

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aread(self):
            return b"Bad Gateway"

    class MockErrorClient:
        def stream(self, method, url, **kwargs):
            return MockErrorStreamResponse()

    provider = PollinationsProvider(client=MockErrorClient())
    with pytest.raises(RuntimeError, match="Pollinations streaming error 502"):
        async for _ in provider.stream(messages=[{"role": "user", "content": "hi"}]):
            pass


def test_pollinations_component_registration() -> None:
    """Verifies Pollinations component registration in Anima context."""
    ctx = Context()
    ctx.llm = LLMService(ctx)

    apply(ctx)

    provider = ctx.llm.get_provider("pollinations")
    assert isinstance(provider, PollinationsProvider)
    assert provider.default_model == "openai"
    assert provider.base_url == "https://text.pollinations.ai/openai"


def test_pollinations_component_integration() -> None:
    """Verifies Pollinations component with custom config options."""
    ctx = Context()
    ctx.llm = LLMService(ctx)

    apply(
        ctx,
        api_key="custom-key",
        base_url="https://text.pollinations.ai/openai/",
        default_model="openai-fast",
    )

    provider = ctx.llm.get_provider("pollinations")
    assert isinstance(provider, PollinationsProvider)
    assert provider.api_key == "custom-key"
    assert provider.default_model == "openai-fast"
    assert provider.base_url == "https://text.pollinations.ai/openai"
