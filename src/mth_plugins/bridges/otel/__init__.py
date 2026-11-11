"""OpenTelemetry bridge component package."""

from mth_plugins.bridges.otel.component import apply
from mth_plugins.bridges.otel.tracer import OtelTracerService, SpanRecord

__all__ = [
    "OtelTracerService",
    "SpanRecord",
    "apply",
]
