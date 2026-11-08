"""OpenRouter model provider for Magitech Harness."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from magitech_harness.agent.cancellation import AbortSignal
from magitech_harness.llm.types import ModelChunk, ModelResponse, UsageData
from magitech_harness.session.events import ToolCallData


def _parse_usage(raw_usage: dict[str, Any] | None) -> UsageData:
    """Parses raw usage dictionary into UsageData instance."""
    if not raw_usage:
        return UsageData()
    return UsageData(
        prompt_tokens=raw_usage.get("prompt_tokens", 0),
        completion_tokens=raw_usage.get("completion_tokens", 0),
        total_tokens=raw_usage.get("total_tokens", 0),
        reasoning_tokens=raw_usage.get("reasoning_tokens", 0),
    )


def _parse_tool_calls(raw_tool_calls: list[dict[str, Any]]) -> list[ToolCallData]:
    """Parses raw tool call dictionaries into ToolCallData instances."""
    tool_calls: list[ToolCallData] = []
    for raw_tc in raw_tool_calls:
        fn = raw_tc.get("function") or {}
        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {"raw": raw_args}
        else:
            parsed_args = raw_args

        tool_calls.append(
            ToolCallData(
                call_id=raw_tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=parsed_args,
            )
        )
    return tool_calls


def _parse_sse_line(line: str) -> tuple[bool, ModelChunk | None]:
    """Parses a single Server-Sent Events line into a ModelChunk.

    Returns:
        A tuple of (is_done, chunk_or_none).
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
        return False, None

    content = stripped.removeprefix("data:").strip()
    if not content:
        return False, None
    if content == "[DONE]":
        return True, None

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False, None

    usage_data = _parse_usage(data.get("usage"))
    choices = data.get("choices") or []
    if not choices:
        if usage_data.total_tokens > 0:
            return False, ModelChunk(usage=usage_data)
        return False, None

    choice = choices[0]
    delta = choice.get("delta") or {}
    text_delta = delta.get("content") or ""
    finish_reason = choice.get("finish_reason")
    tool_calls = _parse_tool_calls(delta.get("tool_calls") or [])

    if text_delta or tool_calls or finish_reason or usage_data.total_tokens > 0:
        return False, ModelChunk(
            text=text_delta,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage_data,
        )
    return False, None


class OpenRouterProvider:
    """LLMProvider implementation for OpenRouter API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        default_model: str = "openai/gpt-4o-mini",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initializes the OpenRouter provider."""
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str | None,
        stream: bool,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Builds the API request payload."""
        effective_messages: list[dict[str, Any]] = []
        if system_prompt and not any(m.get("role") == "system" for m in messages):
            effective_messages.append({"role": "system", "content": system_prompt})
        effective_messages.extend(messages)

        model = kwargs.get("model") or self.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": effective_messages,
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools

        for param in ("temperature", "max_tokens", "top_p"):
            if param in kwargs and kwargs[param] is not None:
                payload[param] = kwargs[param]

        return payload

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generates a completion from OpenRouter."""
        payload = self._build_payload(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream=False,
            kwargs=kwargs,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        client = self._get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenRouter API error {response.status_code}: {response.text}"
            )

        data = response.json()
        choices = data.get("choices") or []
        usage_data = _parse_usage(data.get("usage"))
        if not choices:
            return ModelResponse(
                text="",
                finish_reason="stop",
                raw_response=data,
                usage=usage_data,
            )

        choice = choices[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        tool_calls = _parse_tool_calls(msg.get("tool_calls") or [])
        finish_reason = choice.get("finish_reason") or "stop"
        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=data,
            usage=usage_data,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        signal: AbortSignal | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelChunk]:
        """Streams response chunks from OpenRouter API."""
        if signal is not None:
            signal.throw_if_aborted()

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream=True,
            kwargs=kwargs,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        client = self._get_client()
        try:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                if response.status_code != 200:
                    raw_err = await response.aread()
                    msg = raw_err.decode(errors="replace")
                    raise RuntimeError(
                        f"OpenRouter streaming error {response.status_code}: {msg}"
                    )

                async for raw_line in response.aiter_lines():
                    if signal is not None:
                        signal.throw_if_aborted()

                    is_done, chunk = _parse_sse_line(raw_line)
                    if is_done:
                        break
                    if chunk is not None:
                        yield chunk
        finally:
            if self._client is None:
                await client.aclose()
