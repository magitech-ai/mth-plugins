"""Unit tests for SessionTitleService lifecycle, fallback, and LLM titling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anima import Context
from magitech_harness.llm.service import LLMService

from mth_plugins.sessions.title.service import SessionTitleService


@pytest.fixture
def ctx() -> Context:
    c = Context()
    llm = LLMService(c)
    llm.default_model = "test-model"
    return c


@pytest.mark.asyncio
async def test_session_title_service_fallback_and_llm(ctx: Context) -> None:
    service = SessionTitleService(ctx)

    # 1. Initially no title
    assert service.get_title("s1") is None

    # Mock LLM generation response
    ctx.llm.generate = AsyncMock(
        return_value=SimpleNamespace(text='"Analyze CPU Profile"')
    )

    # Evaluate turn
    title = await service.evaluate_turn("s1", "Why is the server CPU spiking at 100%?")
    assert title == "Why is the server CPU spiking at 100%?"
    assert service.get_state("s1").source == "fallback"

    # Await background LLM tasks
    await asyncio.gather(*service._background_tasks)
    assert service.get_title("s1") == "Analyze CPU Profile"
    assert service.get_state("s1").source == "llm"

    # Second turn evaluation on already titled session
    second_res = await service.evaluate_turn("s1", "Another follow-up turn")
    assert second_res == "Analyze CPU Profile"


@pytest.mark.asyncio
async def test_session_title_pinned_and_restored_protection(ctx: Context) -> None:
    service = SessionTitleService(ctx)

    # 1. Pinned title
    service.set_title("s2", "My Pinned Title", pinned=True)
    assert service.get_title("s2") == "My Pinned Title"
    res = await service.evaluate_turn("s2", "Something totally different")
    assert res == "My Pinned Title"

    # 2. Restored title
    service.set_title("s3", "Resumed Session", restored=True, pinned=False)
    assert service.get_title("s3") == "Resumed Session"
    res3 = await service.evaluate_turn("s3", "Another prompt")
    assert res3 == "Resumed Session"

    # Background generation skips pinned/restored sessions
    await service._generate_llm_title("s2", "New prompt")
    assert service.get_title("s2") == "My Pinned Title"


@pytest.mark.asyncio
async def test_session_title_llm_exceptions_and_no_llm() -> None:
    # Context without LLM service
    empty_ctx = Context()
    service_no_llm = SessionTitleService(empty_ctx)
    t = await service_no_llm.evaluate_turn("s4", "Test prompt without LLM")
    assert t == "Test prompt without LLM"
    assert len(service_no_llm._background_tasks) == 0

    # Call _generate_llm_title without LLM service
    await service_no_llm._generate_llm_title("s4", "some text")
    assert service_no_llm.get_title("s4") == "Test prompt without LLM"

    # Context with failing LLM
    ctx_fail = Context()
    llm = LLMService(ctx_fail)
    llm.generate = AsyncMock(side_effect=RuntimeError("Provider offline"))
    service_fail = SessionTitleService(ctx_fail)
    await service_fail.evaluate_turn("s5", "Testing network resilience")
    await asyncio.gather(*service_fail._background_tasks)
    # Stays on fallback title
    assert service_fail.get_title("s5") == "Testing network resilience"
    assert service_fail.get_state("s5").source == "fallback"

    # Context where LLM returns empty text
    ctx_empty = Context()
    llm_empty = LLMService(ctx_empty)
    llm_empty.generate = AsyncMock(return_value=SimpleNamespace(text=""))
    service_empty = SessionTitleService(ctx_empty)
    await service_empty.evaluate_turn("s6", "Prompt for empty response")
    await asyncio.gather(*service_empty._background_tasks)
    assert service_empty.get_title("s6") == "Prompt for empty response"

    # Context where LLM returns whitespace/symbols only
    ctx_symbols = Context()
    llm_symbols = LLMService(ctx_symbols)
    llm_symbols.generate = AsyncMock(return_value=SimpleNamespace(text='  "###"  '))
    service_symbols = SessionTitleService(ctx_symbols)
    await service_symbols.evaluate_turn("s7", "Prompt for symbols only")
    await asyncio.gather(*service_symbols._background_tasks)
    assert service_symbols.get_title("s7") == "Prompt for symbols only"
