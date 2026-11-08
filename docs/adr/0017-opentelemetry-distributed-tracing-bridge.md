# ADR 0017: OpenTelemetry Distributed Tracing Instrumentation Bridge

## Status
Accepted

## Date
2026-11-08

## Context
Production agent deployments require comprehensive observability into multi-turn conversations, LLM request latencies, token consumption, and tool execution times. Without structured distributed tracing, identifying bottlenecks or diagnosing tool errors across complex asynchronous agent lifecycles requires manual log parsing.

## Decision
1. **OpenTelemetry Tracer Integration**:
   The `opentelemetry-bridge` registers an OpenTelemetry tracer provider and hooks into Anima context events and harness execution waterfalls:
   - **Turn Spans**: Measures duration and attributes of full turn lifecycles (`magitech.turn`).
   - **Provider Spans**: Captures model requests (`magitech.llm.call`), recording model name, prompt token count, completion token count, and streaming TTFT (time-to-first-token).
   - **Tool Spans**: Instruments tool invocations (`magitech.tool.execute`), capturing tool name, execution status, and duration.
2. **Standard GenAI Semantic Conventions**:
   Trace spans adhere to OpenTelemetry semantic conventions for Generative AI systems (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`).
3. **Pluggable Exporters**:
   Support standard OTLP/gRPC and OTLP/HTTP exporters configured via standard environment variables (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`) with an in-memory exporter for testing.

## Consequences
- **Positive**: Standardized observability out of the box with zero proprietary vendor coupling.
- **Positive**: Fine-grained latency breakdowns identifying slow tools or model response bottlenecks.
- **Positive**: Safe no-op fallback when OpenTelemetry SDK is not configured in the host environment.
