"""Pollinations free anonymous model provider for Magitech Harness."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from magitech_harness.agent.cancellation import AbortSignal
from magitech_harness.llm.types import ModelChunk, ModelResponse
from magitech_harness.session.events import ToolCallData


def wire_model_id(model_id: str) -> str:
    """Reduces a harness model slug to the wire id Pollinations publishes."""
    return model_id.removeprefix("pollinations/")


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
    """Parses a single Server-Sent Events line into a ModelChunk."""
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

    choices = data.get("choices") or []
    if not choices:
        return False, None

    choice = choices[0]
    delta = choice.get("delta") or {}
    text_delta = delta.get("content") or ""
    finish_reason = choice.get("finish_reason")
    tool_calls = _parse_tool_calls(delta.get("tool_calls") or [])

    if text_delta or tool_calls or finish_reason:
        return False, ModelChunk(
            text=text_delta,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )
    return False, None


class PollinationsProvider:
    """LLMProvider implementation for Pollinations free anonymous API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://text.pollinations.ai/openai",
        default_model: str = "openai",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initializes the Pollinations provider."""
        self.api_key = api_key or os.getenv("POLLINATIONS_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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

        raw_model = kwargs.get("model") or self.default_model
        model = wire_model_id(raw_model)

        payload: dict[str, Any] = {
            "model": model,
            "messages": effective_messages,
        }
        if stream:
            payload["stream"] = True
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
        """Generates a completion from Pollinations."""
        payload = self._build_payload(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream=False,
            kwargs=kwargs,
        )
        headers = self._build_headers()
        url = f"{self.base_url}/chat/completions"
        client = self._get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code != 200:
            raise RuntimeError(
                f"Pollinations API error {response.status_code}: {response.text}"
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ModelResponse(text="", finish_reason="stop", raw_response=data)

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
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        signal: AbortSignal | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelChunk]:
        """Streams response chunks from Pollinations API."""
        if signal is not None:
            signal.throw_if_aborted()

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream=True,
            kwargs=kwargs,
        )
        headers = self._build_headers()
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
                        f"Pollinations streaming error {response.status_code}: {msg}"
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
