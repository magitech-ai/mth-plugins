"""Anima component entry point for OpenRouter provider."""

from __future__ import annotations

from typing import Any

from anima import Context

from mth_plugins.providers.openrouter.provider import OpenRouterProvider


def apply(
    ctx: Context,
    api_key: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
    default_model: str = "openai/gpt-4o-mini",
    **kwargs: Any,
) -> None:
    """Mounts the OpenRouter provider onto ctx.llm.

    Args:
        ctx: Active Anima Context.
        api_key: Optional API key.
        base_url: API base URL.
        default_model: Default model identifier.
        **kwargs: Unused extra component configuration.
    """
    provider = OpenRouterProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
    )
    ctx.llm.register_provider("openrouter", provider)


apply.inject = ["llm"]  # type: ignore[attr-defined]
