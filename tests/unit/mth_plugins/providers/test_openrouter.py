"""Unit tests for OpenRouter provider and plugin."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from anima import Context
from magitech_harness.llm.service import LLMService

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
        ]
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
async def test_openrouter_provider_tool_calls_variations() -> None:
    """Verifies parsing of valid JSON, non-string, and malformed tool calls."""
    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "foo.txt"}),
                            },
                        },
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "dict_args",
                                "arguments": {"already": "dict"},
                            },
                        },
                        {
                            "id": "call-3",
                            "type": "function",
                            "function": {
                                "name": "bad_json",
                                "arguments": "{invalid json",
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

    provider = OpenRouterProvider(client=mock_client)
    res = await provider.generate(
        messages=[{"role": "user", "content": "run tools"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert res.text == ""
    assert res.finish_reason == "tool_calls"
    assert len(res.tool_calls) == 3
    assert res.tool_calls[0].arguments == {"path": "foo.txt"}
    assert res.tool_calls[1].arguments == {"already": "dict"}
    assert res.tool_calls[2].arguments == {"raw": "{invalid json"}


@pytest.mark.asyncio
async def test_openrouter_provider_empty_choices() -> None:
    """Verifies handling when API returns empty choices."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(client=mock_client)
    res = await provider.generate(messages=[])
    assert res.text == ""
    assert res.tool_calls == []


@pytest.mark.asyncio
async def test_openrouter_provider_error_status() -> None:
    """Verifies that non-200 response raises RuntimeError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_client.post.return_value = mock_resp

    provider = OpenRouterProvider(client=mock_client)
    with pytest.raises(RuntimeError, match="OpenRouter API error 401: Unauthorized"):
        await provider.generate(messages=[])


@pytest.mark.asyncio
async def test_openrouter_provider_default_client_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies default client creation and automatic cleanup."""
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    mock_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_client_instance.post.return_value = mock_resp

    monkeypatch.setattr(httpx, "AsyncClient", lambda: mock_client_instance)

    provider = OpenRouterProvider()
    res = await provider.generate(messages=[{"role": "user", "content": "hi"}])
    assert res.text == "ok"
    mock_client_instance.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_openrouter_plugin_integration() -> None:
    """Verifies mounting OpenRouter plugin into Context."""
    ctx = Context()
    ctx.plugin(LLMService)
    ctx.plugin(apply, api_key="secret-key", default_model="custom/test-model")
    await ctx.flush()

    assert "openrouter" in ctx.llm.providers
    provider = ctx.llm.get_provider("openrouter")
    assert isinstance(provider, OpenRouterProvider)
    assert provider.api_key == "secret-key"
    assert provider.default_model == "custom/test-model"
