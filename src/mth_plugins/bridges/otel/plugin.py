"""Anima plugin entry point for OpenTelemetry distributed tracing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anima import Context
from magitech_harness.tools.service import ToolCallData

from mth_plugins.bridges.otel.tracer import OtelTracerService


def apply(
    ctx: Context,
    service_name: str = "magitech",
    **kwargs: Any,
) -> OtelTracerService:
    """Mounts OpenTelemetry distributed tracing instrumentation onto Anima context."""
    service = OtelTracerService(ctx, service_name=service_name)

    ctx.effect(lambda: service.clear)

    # 1. Turn lifecycle waterfall hook
    async def _on_turn(
        turn_data: Any,
        next_fn: Callable[..., Any],
    ) -> Any:
        session_id = getattr(turn_data, "session_id", None) or (
            turn_data.get("session_id")
            if isinstance(turn_data, dict)
            else "unknown_session"
        )
        turn_id = getattr(turn_data, "turn_id", None) or (
            turn_data.get("turn_id") if isinstance(turn_data, dict) else None
        )
        span = service.start_turn_span(
            session_id=str(session_id), turn_id=str(turn_id) if turn_id else None
        )
        try:
            return await next_fn(turn_data)
        except Exception as exc:
            span.set_error(str(exc))
            raise
        finally:
            span.end()

    # 2. Tool execution waterfall hooks
    async def _on_tools_pre_execute(
        call_data: ToolCallData,
        next_fn: Callable[..., Any],
    ) -> Any:
        service.start_tool_span(call_data.name, call_data.call_id)
        return await next_fn(call_data)

    async def _on_tools_post_execute(
        output: Any,
        call_data: ToolCallData,
        next_fn: Callable[..., Any],
    ) -> Any:
        res = await next_fn(output, call_data)
        is_error = getattr(res, "is_error", False)
        error_msg = getattr(res, "content", None) if is_error else None
        service.end_tool_span(
            call_data.call_id,
            is_error=is_error,
            error_message=str(error_msg) if error_msg else None,
        )
        return res

    ctx.on("agent/turn", _on_turn)
    ctx.on("tools/pre-execute", _on_tools_pre_execute)
    ctx.on("tools/post-execute", _on_tools_post_execute)

    return service
