"""Unit tests for context compaction guard component."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from anima import Context
from magitech_harness.llm.service import LLMService, MockLLMProvider
from magitech_harness.llm.types import ModelResponse
from magitech_harness.session.events import EventType, SessionEvent, ToolCallData
from magitech_harness.session.service import SessionService

from mth_plugins.guards.compaction.compaction import (
    compact_session,
    estimate_history_tokens,
    estimate_tokens,
    find_safe_cut_index,
    summarize_events,
)
from mth_plugins.guards.compaction.component import apply


def _make_event(
    ev_type: EventType | str,
    payload: dict[str, Any],
    session_id: str = "sess_test",
) -> SessionEvent:
    return SessionEvent(
        id=str(uuid.uuid4()),
        session_id=session_id,
        type=ev_type,
        payload=payload,
    )


def test_estimate_tokens() -> None:
    """Verifies token estimation heuristic."""
    assert estimate_tokens("") == 1
    assert estimate_tokens("hello world") >= 1
    long_text = "a" * 400
    assert estimate_tokens(long_text) == 100


def test_estimate_history_tokens() -> None:
    """Verifies token estimation across diverse event types."""
    events = [
        _make_event(
            EventType.USER_MESSAGE,
            {"text": "What is the capital of France?"},
        ),
        _make_event(
            EventType.ASSISTANT_MESSAGE,
            {
                "text": "Let me check.",
                "tool_calls": [
                    ToolCallData(
                        call_id="c1",
                        name="search",
                        arguments={"q": "capital of France"},
                    )
                ],
            },
        ),
        _make_event(
            EventType.TOOL_RESULT,
            {"call_id": "c1", "content": "Paris is the capital of France."},
        ),
        _make_event(
            EventType.COMPACTION_SUMMARY,
            {"summary": "User asked about Paris."},
        ),
        # The retired type is still read from old logs.
        _make_event(
            "session/compaction",
            {"summary": "Older summary."},
        ),
        _make_event(
            EventType.STEP_START,
            {"step_index": 1},
        ),
    ]
    total_tokens = estimate_history_tokens(events)
    assert total_tokens > 10


def test_find_safe_cut_index_empty_and_no_cut() -> None:
    """Verifies safe cut index on empty or insufficient events."""
    assert find_safe_cut_index([], 0) is None
    assert find_safe_cut_index([], 5) is None

    events = [
        _make_event(EventType.USER_MESSAGE, {"text": "hi"}),
    ]
    # Cut index 0 or negative
    assert find_safe_cut_index(events, 0) is None


def test_find_safe_cut_index_with_tool_pairing() -> None:
    """Verifies finding boundary that respects tool call/result pairing."""
    events = [
        _make_event(EventType.USER_MESSAGE, {"text": "msg 1"}),
        _make_event(
            EventType.ASSISTANT_MESSAGE,
            {
                "tool_calls": [ToolCallData(call_id="c1", name="bash", arguments={})],
            },
        ),
        _make_event(
            EventType.TOOL_RESULT,
            {"call_id": "c1", "content": "ok"},
        ),
        _make_event(
            EventType.ASSISTANT_MESSAGE,
            {
                "tool_calls": [ToolCallData(call_id="c2", name="bash", arguments={})],
            },
        ),
        # c2 tool result not in events yet
        _make_event(EventType.STEP_START, {"step_index": 2}),
    ]

    # Target cut index 4 includes c2 call without c2 result -> unsafe!
    # Should back up to index 3 (which includes c1 call and c1 result -> safe!)
    cut = find_safe_cut_index(events, 4)
    assert cut == 3

    # If completely unbalanced
    unbalanced = [
        _make_event(
            EventType.ASSISTANT_MESSAGE,
            {
                "tool_calls": [ToolCallData(call_id="c1", name="bash", arguments={})],
            },
        ),
        _make_event(EventType.STEP_START, {"step_index": 1}),
    ]
    assert find_safe_cut_index(unbalanced, 1) is None


@pytest.mark.asyncio
async def test_summarize_events_offline() -> None:
    """Verifies deterministic summarization when LLM is unavailable."""
    events = [
        _make_event(EventType.USER_MESSAGE, {"text": "Write a report"}),
        _make_event(
            EventType.ASSISTANT_MESSAGE,
            {
                "text": "Running analysis",
                "tool_calls": [
                    ToolCallData(call_id="c1", name="analyze", arguments={})
                ],
            },
        ),
        _make_event(
            EventType.TOOL_RESULT,
            {"call_id": "c1", "content": "Report data"},
        ),
        _make_event(
            EventType.COMPACTION_SUMMARY,
            {"summary": "Previous summary"},
        ),
        # The retired type still formats from old logs.
        _make_event(
            "session/compaction",
            {"summary": "Older summary"},
        ),
    ]
    summary = await summarize_events(events)
    assert "User: Write a report" in summary
    assert "Assistant: Running analysis" in summary
    assert "Tool call 'analyze'" in summary
    assert "Prior Summary: Previous summary" in summary
    assert "Prior Summary: Older summary" in summary


@pytest.mark.asyncio
async def test_summarize_events_with_llm() -> None:
    """Verifies LLM-based summarization when LLM service is available."""
    ctx = Context()
    ctx.use(LLMService)
    await ctx.flush()

    mock_provider = MockLLMProvider(
        [ModelResponse(text="Concise executive summary of conversation.")]
    )
    ctx.llm.register_provider("mock", mock_provider)

    events = [
        _make_event(EventType.USER_MESSAGE, {"text": "Help me build an agent"}),
    ]
    summary = await summarize_events(events, ctx=ctx)
    assert summary == "Concise executive summary of conversation."


@pytest.mark.asyncio
async def test_summarize_events_with_llm_failure_fallback() -> None:
    """Verifies graceful fallback to offline summary if LLM call fails."""
    ctx = Context()
    ctx.use(LLMService)
    await ctx.flush()

    class FailingProvider:
        async def generate(self, *args, **kwargs):
            raise RuntimeError("API timeout")

    ctx.llm.register_provider("failing", FailingProvider())

    events = [
        _make_event(EventType.USER_MESSAGE, {"text": "Fallback test"}),
    ]
    summary = await summarize_events(events, ctx=ctx)
    assert "User: Fallback test" in summary


@pytest.mark.asyncio
async def test_compact_session_success() -> None:
    """Verifies compacting session creates a compaction/summary event."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    session = ctx.sessions.create("sess_compaction_1")
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Step 1"})
    ctx.sessions.log_event(
        session, EventType.ASSISTANT_MESSAGE, {"text": "Step 1 answer"}
    )
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Step 2"})
    ctx.sessions.log_event(
        session, EventType.ASSISTANT_MESSAGE, {"text": "Step 2 answer"}
    )

    res = await compact_session(ctx, session, target_ratio=0.5)
    assert res["compacted"] is True
    assert res["compacted_count"] == 2
    assert "summary" in res

    # Verify event logged to session
    assert session.events[-1].type == EventType.COMPACTION_SUMMARY
    assert session.events[-1].payload["compacted_count"] == 2

    # The summary event is recorded, but derive_messages does not fold
    # compaction/summary into the transcript yet: that fold belongs to
    # the P2-6 derive rewrite. Until then the transcript still carries
    # the pre-cut messages.
    msgs = session.derive_messages()
    assert len(msgs) == 4
    assert msgs[0]["content"] == "Step 1"
    assert msgs[1]["content"] == "Step 1 answer"
    assert msgs[2]["content"] == "Step 2"
    assert msgs[3]["content"] == "Step 2 answer"


@pytest.mark.asyncio
async def test_compact_session_not_compacted() -> None:
    """Verifies compact_session returns compacted=False when history is too short."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    session = ctx.sessions.create("sess_short")
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Single msg"})

    res = await compact_session(ctx, session)
    assert res["compacted"] is False
    assert "reason" in res


@pytest.mark.asyncio
async def test_component_waterfall_session_compact() -> None:
    """Verifies session/compact waterfall trigger."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    apply(ctx)

    session = ctx.sessions.create("sess_manual_compact")
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Turn 1"})
    ctx.sessions.log_event(session, EventType.ASSISTANT_MESSAGE, {"text": "Answer 1"})
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Turn 2"})

    res = await ctx.waterfall(
        "session/compact",
        {"session": session, "status": "requested"},
        default_handler=lambda p: p,
    )

    assert res["compacted"] is True
    assert "summary" in res

    # Test waterfall without session
    res_no_sess = await ctx.waterfall(
        "session/compact",
        {"status": "requested"},
        default_handler=lambda p: p,
    )
    assert res_no_sess["compacted"] is False
    assert res_no_sess["error"] == "No session provided"


@pytest.mark.asyncio
async def test_component_waterfall_agent_pre_step_pressure() -> None:
    """Verifies agent/pre-step waterfall triggers compaction on token pressure."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    # Configure very low max_tokens (e.g. 5 tokens) to trigger compaction
    apply(ctx, max_tokens=5, target_ratio=0.5)

    session = ctx.sessions.create("sess_pressure")
    ctx.sessions.log_event(
        session, EventType.USER_MESSAGE, {"text": "Long user message with words"}
    )
    ctx.sessions.log_event(
        session, EventType.ASSISTANT_MESSAGE, {"text": "Long assistant response"}
    )
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Next question"})

    # Trigger pre-step
    res = await ctx.waterfall(
        "agent/pre-step",
        {"action": "continue", "step_index": 1, "session": session},
        default_handler=lambda p: p,
    )

    assert res["action"] == "continue"
    assert session.events[-1].type == EventType.COMPACTION_SUMMARY


@pytest.mark.asyncio
async def test_summarize_events_edge_cases() -> None:
    """Verifies edge cases in formatting bullets and empty LLM response."""
    # Assistant message with only tool calls (no text)
    ev_tool_only = _make_event(
        EventType.ASSISTANT_MESSAGE,
        {
            "text": "",
            "tool_calls": [ToolCallData(call_id="c1", name="grep", arguments={})],
        },
    )
    # Assistant message with empty payload
    ev_empty_asst = _make_event(EventType.ASSISTANT_MESSAGE, {})
    # Ignored event type
    ev_turn = _make_event(EventType.TURN_START, {})

    summary = await summarize_events([ev_tool_only, ev_empty_asst, ev_turn])
    assert "Tool call 'grep'" in summary

    # LLM returning whitespace-only text
    ctx = Context()
    ctx.use(LLMService)
    await ctx.flush()
    ctx.llm.register_provider("mock", MockLLMProvider([ModelResponse(text="   ")]))
    summary_empty_llm = await summarize_events([ev_tool_only], ctx=ctx)
    assert "[Prior Context Summary]" in summary_empty_llm


@pytest.mark.asyncio
async def test_compact_session_unbalanced_boundary() -> None:
    """Verifies compact_session when no safe boundary can be found."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    session = ctx.sessions.create("sess_unbalanced")
    # 2 events: first has unresolved tool call, second is turn start.
    # Append takes plain JSON data: a model instance is not lossless JSON.
    ctx.sessions.log_event(
        session,
        EventType.ASSISTANT_MESSAGE,
        {"tool_calls": [{"call_id": "c_unres", "name": "tool", "arguments": {}}]},
    )
    ctx.sessions.log_event(session, EventType.STEP_START, {"step_index": 1})

    res = await compact_session(ctx, session, target_ratio=0.5)
    assert res["compacted"] is False
    assert "No balanced boundary" in res["reason"]


@pytest.mark.asyncio
async def test_component_waterfall_agent_pre_step_below_threshold() -> None:
    """Verifies pre-step does not compact when token estimate is below max."""
    ctx = Context()
    ctx.use(SessionService)
    await ctx.flush()

    apply(ctx, max_tokens=10000)

    session = ctx.sessions.create("sess_small")
    ctx.sessions.log_event(session, EventType.USER_MESSAGE, {"text": "Short message"})

    res = await ctx.waterfall(
        "agent/pre-step",
        {"action": "continue", "step_index": 1, "session": session},
        default_handler=lambda p: p,
    )
    assert res["action"] == "continue"
    assert session.events[-1].type == EventType.USER_MESSAGE


@pytest.mark.asyncio
async def test_component_waterfall_agent_pre_step_no_session() -> None:
    """Verifies agent/pre-step behaves normally when session is not in payload."""
    ctx = Context()
    apply(ctx)

    res = await ctx.waterfall(
        "agent/pre-step",
        {"action": "continue", "step_index": 1},
        default_handler=lambda p: p,
    )
    assert res["action"] == "continue"
