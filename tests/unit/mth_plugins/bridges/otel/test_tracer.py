"""Unit tests for SpanRecord and OtelTracerService."""

from anima import Context

from mth_plugins.bridges.otel.tracer import OtelTracerService, SpanRecord


def test_span_record_lifecycle() -> None:
    t0 = 1000.0
    span = SpanRecord(name="test.span", attributes={"key": "val"}, start_time=t0)
    assert span.name == "test.span"
    assert span.attributes["key"] == "val"
    assert span.duration is None
    assert span.status == "OK"

    span.set_attribute("extra", 123)
    assert span.attributes["extra"] == 123

    span.set_error("Something broke")
    assert span.status == "ERROR"
    assert span.error_message == "Something broke"

    span.end(end_time=1005.5)
    assert span.duration == 5.5

    # Ending again does not overwrite
    span.end(end_time=1010.0)
    assert span.duration == 5.5


def test_tracer_service_turn_spans() -> None:
    ctx = Context()
    svc = OtelTracerService(ctx, service_name="magitech-test")
    assert svc.service_name == "magitech-test"

    # Turn span with auto turn_id
    span1 = svc.start_turn_span(session_id="sess_123")
    assert span1.name == "magitech.turn"
    assert span1.attributes["magitech.session.id"] == "sess_123"
    assert span1.attributes["magitech.turn.id"] == "turn_1"
    assert len(svc.recorded_spans) == 1

    # Turn span with custom turn_id
    span2 = svc.start_turn_span(session_id="sess_123", turn_id="turn_custom")
    assert span2.attributes["magitech.turn.id"] == "turn_custom"
    assert len(svc.recorded_spans) == 2


def test_tracer_service_llm_spans() -> None:
    ctx = Context()
    svc = OtelTracerService(ctx)

    # 1. Without prompt tokens
    span1 = svc.start_llm_span(model="anthropic/claude-3-opus", stream=True)
    assert span1.name == "magitech.llm.call"
    assert span1.attributes["gen_ai.request.model"] == "anthropic/claude-3-opus"
    assert span1.attributes["gen_ai.request.stream"] is True
    assert "gen_ai.usage.input_tokens" not in span1.attributes

    # 2. With prompt tokens
    span2 = svc.start_llm_span(model="openai/gpt-4o", stream=False, prompt_tokens=512)
    assert span2.attributes["gen_ai.usage.input_tokens"] == 512
    assert span2.attributes["gen_ai.request.stream"] is False


def test_tracer_service_tool_spans() -> None:
    ctx = Context()
    svc = OtelTracerService(ctx)

    span1 = svc.start_tool_span("read_file", "call_1")
    assert span1.name == "magitech.tool.execute"
    assert span1.attributes["magitech.tool.name"] == "read_file"
    assert "call_1" in svc._active_spans

    # End tool span successfully
    ended1 = svc.end_tool_span("call_1", is_error=False)
    assert ended1 is span1
    assert ended1.status == "OK"
    assert "call_1" not in svc._active_spans

    # End tool span with error
    span2 = svc.start_tool_span("bash", "call_2")
    ended2 = svc.end_tool_span("call_2", is_error=True, error_message="Command failed")
    assert ended2 is span2
    assert ended2.status == "ERROR"
    assert ended2.error_message == "Command failed"

    # End tool span with error and default message
    span3 = svc.start_tool_span("edit_file", "call_3")
    ended3 = svc.end_tool_span("call_3", is_error=True)
    assert ended3 is span3
    assert ended3.error_message == "Tool execution error"

    # End non-existent call_id
    assert svc.end_tool_span("call_unknown") is None

    # Clear spans
    svc.clear()
    assert len(svc.recorded_spans) == 0
    assert len(svc._active_spans) == 0
