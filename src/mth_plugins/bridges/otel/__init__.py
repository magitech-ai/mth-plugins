"""OpenTelemetry bridge plugin package."""

from mth_plugins.bridges.otel.plugin import apply
from mth_plugins.bridges.otel.tracer import OtelTracerService, SpanRecord

__all__ = [
    "OtelTracerService",
    "SpanRecord",
    "apply",
]
