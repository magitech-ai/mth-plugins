"""Anima plugin entry point for Pollinations model provider."""

from __future__ import annotations

from typing import Any

from anima import Context

from mth_plugins.providers.pollinations.provider import PollinationsProvider


def apply(
    ctx: Context,
    api_key: str | None = None,
    base_url: str = "https://text.pollinations.ai/openai",
    default_model: str = "openai",
    **kwargs: Any,
) -> None:
    """Mounts the Pollinations provider onto ctx.llm.

    Args:
        ctx: Active Anima Context.
        api_key: Optional API key (Pollinations works anonymously without one).
        base_url: API base URL.
        default_model: Default model identifier.
        **kwargs: Unused extra plugin configuration.
    """
    provider = PollinationsProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
    )
    ctx.llm.register_provider("pollinations", provider)


apply.inject = ["llm"]  # type: ignore[attr-defined]
