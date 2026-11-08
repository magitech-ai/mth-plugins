"""Unit tests for OpenRouter provider and plugin."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from anima import Context
from magitech_harness.agent.cancellation import AbortError, AbortSignal
from magitech_harness.llm.service import LLMService
from magitech_harness.llm.types import ModelChunk

from mth_plugins.providers.openrouter.plugin import apply
from mth_plugins.providers.openrouter.provider import OpenRouterProvider


@pytest.mark.asyncio
async def test_openrouter_provider_generate_text() -> None:
    """Verifies generating text response from OpenRouter."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello Magitech!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 15,
            "total_tokens": 20,
        },
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(
        api_key="test-key",
        client=mock_client,
    )

    res = await provider.generate(
        messages=[{"role": "user", "content": "Hi"}],
        system_prompt="You are a helpful assistant.",
        temperature=0.7,
        max_tokens=100,
        top_p=0.9,
    )

    assert res.text == "Hello Magitech!"
    assert res.finish_reason == "stop"
    assert res.tool_calls == []
    assert res.usage.total_tokens == 20

    # Check payload sent to mock_client.post
    call_args = mock_client.post.call_args
    assert call_args is not None
    payload = call_args.kwargs["json"]
    assert payload["model"] == "openai/gpt-4o-mini"
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_openrouter_provider_generate_with_existing_system_message() -> None:
    """Verifies that system prompt is not duplicated if already present in messages."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Done",
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

    provider = OpenRouterProvider(client=mock_client)
    res = await provider.generate(
        messages=[
            {"role": "system", "content": "Existing system prompt"},
            {"role": "user", "content": "Task"},
        ],
        system_prompt="New prompt",
        model="custom/model",
    )

    assert res.text == "Done"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["model"] == "custom/model"
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["content"] == "Existing system prompt"


@pytest.mark.asyncio
async def test_openrouter_provider_generate_tool_calls() -> None:
    """Verifies parsing tool calls from model response."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Running command",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "echo hello"}',
                            },
                        },
                        {
                            "id": "call_456",
                            "type": "function",
                            "function": {
                                "name": "invalid_json_tool",
                                "arguments": "{bad_json",
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

    provider = OpenRouterProvider(api_key="test-key", client=mock_client)
    res = await provider.generate(
        messages=[{"role": "user", "content": "Run echo"}],
        tools=[{"type": "function", "function": {"name": "bash"}}],
    )

    assert res.text == "Running command"
    assert len(res.tool_calls) == 2
    assert res.tool_calls[0].call_id == "call_123"
    assert res.tool_calls[0].name == "bash"
    assert res.tool_calls[0].arguments == {"command": "echo hello"}

    # Invalid json parsed as raw
    assert res.tool_calls[1].call_id == "call_456"
    assert res.tool_calls[1].name == "invalid_json_tool"
    assert res.tool_calls[1].arguments == {"raw": "{bad_json"}


@pytest.mark.asyncio
async def test_openrouter_provider_generate_empty_choices() -> None:
    """Verifies handling when choices list is empty."""
    mock_response_data = {"choices": []}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(api_key="test-key", client=mock_client)
    res = await provider.generate(messages=[{"role": "user", "content": "Hi"}])
    assert res.text == ""
    assert res.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openrouter_provider_generate_error() -> None:
    """Verifies error handling on non-200 status codes."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(api_key="invalid-key", client=mock_client)
    with pytest.raises(RuntimeError, match="OpenRouter API error 401: Unauthorized"):
        await provider.generate(messages=[{"role": "user", "content": "Hi"}])


@pytest.mark.asyncio
async def test_openrouter_provider_default_client_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that an internally created client is closed after generate."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(api_key="test-key", client=None)
    monkeypatch.setattr(provider, "_get_client", lambda: mock_client)

    await provider.generate(messages=[{"role": "user", "content": "Hi"}])
    mock_client.aclose.assert_awaited_once()


def test_openrouter_provider_default_get_client() -> None:
    """Verifies _get_client returns httpx.AsyncClient if client is None."""
    provider = OpenRouterProvider()
    client = provider._get_client()
    assert isinstance(client, httpx.AsyncClient)


def test_openrouter_plugin_registration() -> None:
    """Verifies OpenRouter plugin registration in Anima context."""
    ctx = Context()
    ctx.llm = LLMService(ctx)

    apply(ctx)

    provider = ctx.llm.get_provider("openrouter")
    assert isinstance(provider, OpenRouterProvider)
    assert provider.default_model == "openai/gpt-4o-mini"


def test_openrouter_plugin_integration() -> None:
    """Verifies OpenRouter plugin with config options."""
    ctx = Context()
    ctx.llm = LLMService(ctx)

    apply(
        ctx,
        api_key="secret-key",
        base_url="https://custom.openrouter.ai/v1",
        default_model="custom/test-model",
    )

    provider = ctx.llm.get_provider("openrouter")
    assert isinstance(provider, OpenRouterProvider)
    assert provider.api_key == "secret-key"
    assert provider.default_model == "custom/test-model"


@pytest.mark.asyncio
async def test_openrouter_provider_stream_chunks() -> None:
    """Verifies streaming token deltas and tool calls from SSE lines."""
    tc_stream = {
        "id": "c_stream",
        "function": {"name": "bash", "arguments": json.dumps({"command": "ls"})},
    }
    tc_raw = {
        "id": "c_raw",
        "function": {"name": "invalid", "arguments": "{not-json"},
    }
    tc_dict = {
        "id": "c_dict",
        "function": {"name": "dict", "arguments": {"foo": "bar"}},
    }
    chunk_tools = json.dumps(
        {"choices": [{"delta": {"tool_calls": [tc_stream, tc_raw, tc_dict]}}]}
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
        f"data: {chunk_tools}",
        f"data: {chunk_world}",
        (
            'data: {"usage": {"prompt_tokens": 10, '
            '"completion_tokens": 20, "total_tokens": 30}}'
        ),
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

    provider = OpenRouterProvider(api_key="test-key", client=MockClient())
    chunks: list[ModelChunk] = [
        c
        async for c in provider.stream(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="sys prompt",
            model="custom/model-stream",
            tools=[{"type": "function", "function": {"name": "bash"}}],
            temperature=0.5,
            max_tokens=50,
            top_p=0.8,
        )
    ]

    assert len(chunks) == 4
    assert chunks[0].text == "Hello "
    assert len(chunks[1].tool_calls) == 3
    assert chunks[1].tool_calls[0].name == "bash"
    assert chunks[1].tool_calls[0].arguments == {"command": "ls"}
    assert chunks[1].tool_calls[1].name == "invalid"
    assert chunks[1].tool_calls[1].arguments == {"raw": "{not-json"}
    assert chunks[1].tool_calls[2].name == "dict"
    assert chunks[1].tool_calls[2].arguments == {"foo": "bar"}
    assert chunks[2].text == "World!"
    assert chunks[2].finish_reason == "stop"
    assert chunks[3].usage.total_tokens == 30

    payload = captured_kwargs["json"]
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["model"] == "custom/model-stream"
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 50
    assert payload["top_p"] == 0.8
    assert payload["tools"] == [{"type": "function", "function": {"name": "bash"}}]
    assert payload["messages"][0]["role"] == "system"

    # Test abort signal before start
    signal = AbortSignal()
    signal.abort()
    with pytest.raises(AbortError, match="Operation was aborted"):
        async for _ in provider.stream(messages=[], signal=signal):
            pass


@pytest.mark.asyncio
async def test_openrouter_provider_stream_mid_stream_abort() -> None:
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

    provider = OpenRouterProvider(api_key="test-key", client=MockClient())
    with pytest.raises(AbortError, match="Operation was aborted"):
        async for _ in provider.stream(
            messages=[{"role": "user", "content": "hi"}], signal=signal
        ):
            pass


@pytest.mark.asyncio
async def test_openrouter_provider_stream_default_client_close(
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

    provider = OpenRouterProvider(api_key="test-key", client=None)
    monkeypatch.setattr(provider, "_get_client", MockInternalClient)

    async for _ in provider.stream(messages=[{"role": "user", "content": "hi"}]):
        pass

    assert client_closed is True


@pytest.mark.asyncio
async def test_openrouter_provider_stream_error() -> None:
    """Verifies streaming handles non-200 HTTP status code."""

    class MockErrorStreamResponse:
        status_code = 500

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aread(self):
            return b"Internal Server Error"

    class MockErrorClient:
        def stream(self, method, url, **kwargs):
            return MockErrorStreamResponse()

    provider = OpenRouterProvider(api_key="test-key", client=MockErrorClient())
    with pytest.raises(RuntimeError, match="OpenRouter streaming error 500"):
        async for _ in provider.stream(messages=[{"role": "user", "content": "hi"}]):
            pass
