"""OpenTelemetry distributed tracing service and GenAI span instrumentation."""

from __future__ import annotations

import time
from typing import Any

from anima import Context, Service

GENAI_SYSTEM = "magitech"


class SpanRecord:
    """Represents an active or completed trace span."""

    def __init__(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        start_time: float | None = None,
    ) -> None:
        self.name = name
        self.attributes: dict[str, Any] = attributes or {}
        self.start_time: float = start_time if start_time is not None else time.time()
        self.end_time: float | None = None
        self.status: str = "OK"
        self.error_message: str | None = None

    @property
    def duration(self) -> float | None:
        """Returns duration in seconds if span has ended, else None."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    def set_attribute(self, key: str, value: Any) -> None:
        """Adds or updates a span attribute."""
        self.attributes[key] = value

    def set_error(self, message: str) -> None:
        """Marks the span status as ERROR with an error message."""
        self.status = "ERROR"
        self.error_message = message

    def end(self, end_time: float | None = None) -> None:
        """Ends the span and computes duration."""
        if self.end_time is None:
            self.end_time = end_time if end_time is not None else time.time()


class OtelTracerService(Service):
    """Tracer service providing OpenTelemetry GenAI spans and observability."""

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(ctx, "otel")
        self.service_name = (config or {}).get("service_name") or "magitech"
        self.recorded_spans: list[SpanRecord] = []
        self._active_spans: dict[str, SpanRecord] = {}

    def start_turn_span(
        self, session_id: str, turn_id: str | None = None
    ) -> SpanRecord:
        """Starts a span for an agent turn."""
        t_id = turn_id or f"turn_{len(self.recorded_spans) + 1}"
        span = SpanRecord(
            name="magitech.turn",
            attributes={
                "magitech.session.id": session_id,
                "magitech.turn.id": t_id,
                "gen_ai.system": GENAI_SYSTEM,
            },
        )
        self.recorded_spans.append(span)
        return span

    def start_llm_span(
        self,
        model: str,
        stream: bool = True,
        prompt_tokens: int | None = None,
    ) -> SpanRecord:
        """Starts a span conforming to GenAI conventions for model inference."""
        attrs: dict[str, Any] = {
            "gen_ai.system": GENAI_SYSTEM,
            "gen_ai.request.model": model,
            "gen_ai.request.stream": stream,
        }
        if prompt_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = prompt_tokens

        span = SpanRecord(name="magitech.llm.call", attributes=attrs)
        self.recorded_spans.append(span)
        return span

    def start_tool_span(self, tool_name: str, call_id: str) -> SpanRecord:
        """Starts a span for a tool execution."""
        span = SpanRecord(
            name="magitech.tool.execute",
            attributes={
                "magitech.tool.name": tool_name,
                "magitech.tool.call_id": call_id,
                "gen_ai.system": GENAI_SYSTEM,
            },
        )
        self._active_spans[call_id] = span
        self.recorded_spans.append(span)
        return span

    def end_tool_span(
        self,
        call_id: str,
        is_error: bool = False,
        error_message: str | None = None,
    ) -> SpanRecord | None:
        """Completes an active tool execution span."""
        span = self._active_spans.pop(call_id, None)
        if span is not None:
            if is_error:
                span.set_error(error_message or "Tool execution error")
            span.end()
        return span

    def clear(self) -> None:
        """Clears recorded spans and active span tracking."""
        self.recorded_spans.clear()
        self._active_spans.clear()
