# 0003. Anonymous Keyless Model Provider Architecture

Date: 2026-11-07
Status: accepted

## Context

Developers and automated CI pipelines need the ability to run functional agent tests, evaluation suites, and interactive sessions without requiring paid API keys, account registration, or manual credential provisioning.

## Decision

We implement a dedicated anonymous model provider plugin (`pollinations-provider`):
1. **Keyless Anonymous Access**: When no API key is configured or an empty string is provided, the provider completely omits the HTTP `Authorization` header rather than transmitting an empty bearer token.
2. **Wire Model ID Normalization**: The provider normalizes model slugs by stripping namespace prefixes (`pollinations/openai` -> `openai`) before dispatching to the wire.
3. **Full Protocol Support**: Implements both `generate` and `stream` methods of the `LLMProvider` protocol, parsing server-sent events (SSE), extracting reasoning/deliberation deltas, relaying OpenAI tool calls, and honoring `AbortSignal` cancellation.

## Consequences

- Users can immediately test, run, and evaluate the full harness out of the box with zero credentials.
- Test suites can verify real end-to-end model turns anonymously without leaking secrets in CI environments.
- Relies on external public anonymous service availability and rate limits.
