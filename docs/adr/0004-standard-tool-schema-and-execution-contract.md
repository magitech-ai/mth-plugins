# 0004. Standard Tool Schema and Execution Contract

Date: 2026-11-07
Status: accepted

## Context

Pluggable domain tools need a consistent interface for schema discovery by language models, input validation, and execution. Divergent tool formats or proprietary schemas complicate tool registration, prevent cross-model compatibility, and risk unconstrained execution environments.

## Decision

We enforce a unified `ToolDefinition` specification across all marketplace tools:
1. Every tool exports a `ToolDefinition` instance specifying its `name`, human-readable `description`, standard JSON Schema `parameters` dictionary, and an executable handler (`handler`).
2. Tools support both synchronous and asynchronous execution handlers; the tool service normalizes execution asynchronously.
3. System tools that interact with the host environment enforce safe execution boundaries (e.g. `read-file-tool` and filesystem tools enforce base path sandboxing to prevent directory traversal outside allowed roots).
4. Tool results return standardized string outputs or raise explicit execution errors that are formatted into model-visible tool result events without crashing the harness.

## Consequences

- All marketplace tools seamlessly map to standard OpenAI-compatible function calling schemas without model-specific shims.
- Tool schemas are verified during unit testing with 100% statement and branch coverage.
- Authors must define explicit JSON Schema parameter dictionaries for each exposed tool.
