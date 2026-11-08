"""OpenRouter model provider for Magitech Harness."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from magitech_harness.llm.types import ModelResponse
from magitech_harness.session.events import ToolCallData


class OpenRouterProvider:
    """LLMProvider implementation for OpenRouter API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        default_model: str = "openai/gpt-4o-mini",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initializes the OpenRouter provider.

        Args:
            api_key: Optional OpenRouter API key. Falls back to OPENROUTER_API_KEY env.
            base_url: API base URL.
            default_model: Model to use when not specified in kwargs.
            client: Optional pre-configured httpx.AsyncClient instance.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient()

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generates a completion from OpenRouter.

        Args:
            messages: List of message dictionaries.
            tools: Optional tool schemas available to model.
            system_prompt: Optional system prompt to prepend.
            **kwargs: Extra model parameters (model, temperature, etc.).

        Returns:
            ModelResponse containing text and any requested tool calls.

        Raises:
            RuntimeError: If OpenRouter API returns a non-200 status code.
        """
        effective_messages: list[dict[str, Any]] = []
        if system_prompt and not any(m.get("role") == "system" for m in messages):
            effective_messages.append({"role": "system", "content": system_prompt})
        effective_messages.extend(messages)

        model = kwargs.get("model") or self.default_model

        payload: dict[str, Any] = {
            "model": model,
            "messages": effective_messages,
        }
        if tools:
            payload["tools"] = tools

        for param in ("temperature", "max_tokens", "top_p"):
            if param in kwargs and kwargs[param] is not None:
                payload[param] = kwargs[param]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"
        client = self._get_client()
        try:
            response = await client.post(url, headers=headers, json=payload)
        finally:
            # If client was locally created, close it
            if self._client is None:
                await client.aclose()

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenRouter API error {response.status_code}: {response.text}"
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ModelResponse(text="", finish_reason="stop", raw_response=data)

        choice = choices[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""

        tool_calls: list[ToolCallData] = []
        for raw_tc in msg.get("tool_calls") or []:
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

        finish_reason = choice.get("finish_reason") or "stop"
        return ModelResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_response=data,
        )
