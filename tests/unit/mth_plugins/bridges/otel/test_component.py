"""Unit tests for OpenTelemetry bridge component and waterfalls."""

from types import SimpleNamespace
from typing import Any

import pytest
from anima import Context
from magitech_harness.tools.service import ToolCallData, ToolResultData

from mth_plugins.bridges.otel.component import apply


@pytest.fixture
def ctx() -> Context:
    return Context()


@pytest.mark.asyncio
async def test_component_apply_and_turn_waterfall(ctx: Context) -> None:
    service = apply(ctx)
    assert service is not None

    # 1. Turn with dict data
    turn_dict = {"session_id": "sess_100", "turn_id": "t_1"}
    res1 = await ctx.waterfall(
        "agent/turn", turn_dict, default_handler=lambda td: "turn_done"
    )
    assert res1 == "turn_done"
    assert len(service.recorded_spans) == 1
    assert service.recorded_spans[0].status == "OK"
    assert service.recorded_spans[0].duration is not None

    # 2. Turn with object data
    turn_obj = SimpleNamespace(session_id="sess_200", turn_id="t_2")
    res2 = await ctx.waterfall(
        "agent/turn", turn_obj, default_handler=lambda td: "turn2_done"
    )
    assert res2 == "turn2_done"
    assert len(service.recorded_spans) == 2
    assert service.recorded_spans[1].attributes["magitech.session.id"] == "sess_200"

    # 3. Turn with fallback unknown session
    res3 = await ctx.waterfall(
        "agent/turn", "raw_turn", default_handler=lambda td: "turn3_done"
    )
    assert res3 == "turn3_done"
    assert (
        service.recorded_spans[2].attributes["magitech.session.id"] == "unknown_session"
    )

    # 4. Turn raising exception -> span marked as ERROR and re-raised
    async def failing_turn(td: Any) -> None:
        raise RuntimeError("Turn failed")

    with pytest.raises(RuntimeError, match="Turn failed"):
        await ctx.waterfall("agent/turn", turn_dict, default_handler=failing_turn)

    err_span = service.recorded_spans[-1]
    assert err_span.status == "ERROR"
    assert err_span.error_message == "Turn failed"
    assert err_span.duration is not None


@pytest.mark.asyncio
async def test_component_tools_waterfall(ctx: Context) -> None:
    service = apply(ctx)

    # 1. Tool execution success
    call_success = ToolCallData(
        call_id="call_ok", name="read_file", arguments={"path": "a.txt"}
    )
    await ctx.waterfall("tools/pre-execute", call_success, default_handler=lambda c: c)
    assert "call_ok" in service._active_spans

    ok_result = ToolResultData(
        call_id="call_ok", name="read_file", content="file data", is_error=False
    )
    await ctx.waterfall(
        "tools/post-execute", ok_result, call_success, default_handler=lambda r, c: r
    )

    assert "call_ok" not in service._active_spans
    tool_span = next(
        s for s in service.recorded_spans if s.name == "magitech.tool.execute"
    )
    assert tool_span.status == "OK"
    assert tool_span.duration is not None

    # 2. Tool execution failure
    call_err = ToolCallData(
        call_id="call_err", name="bash", arguments={"command": "false"}
    )
    await ctx.waterfall("tools/pre-execute", call_err, default_handler=lambda c: c)

    err_result = ToolResultData(
        call_id="call_err", name="bash", content="Exit 1", is_error=True
    )
    await ctx.waterfall(
        "tools/post-execute", err_result, call_err, default_handler=lambda r, c: r
    )

    err_span = next(
        s
        for s in service.recorded_spans
        if s.attributes.get("magitech.tool.call_id") == "call_err"
    )
    assert err_span.status == "ERROR"
    assert err_span.error_message == "Exit 1"
