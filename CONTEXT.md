# MTH Plugins

The official extensible marketplace containing pluggable model providers, domain tools, guardrails, and compaction policies for the Magitech Harness.

## Language

### Marketplace & Distribution

**Plugin**:
A packaged Python module adhering to the manifest specification that mounts capabilities onto an Anima context.
_Avoid_: Extension, addon, module

**Manifest**:
A JSON document (`manifest.json`) declaring a plugin's identity, version, classification types, entry point, and dependencies.
_Avoid_: Spec, descriptor, config

**Catalog**:
The centralized index (`index.json`) mapping plugin names to their manifest locations and metadata.
_Avoid_: Registry, marketplace database, store

### Capability Seams

**Provider**:
A plugin that implements the `LLMProvider` protocol to interface with external model APIs for text generation and streaming.
_Avoid_: Adapter, model backend, driver

**Tool**:
A callable capability exposed to language models with JSON schema definitions and typed execution handlers.
_Avoid_: Function, spell, action

**Tool Definition**:
The data structure declaring a tool's name, description, JSON schema parameters, and execution callable.
_Avoid_: Tool spec, tool signature, function metadata

**Execution Backend**:
The abstraction mediating subprocess execution and filesystem operations across local, containerized, or sandboxed environments.
_Avoid_: Shell runner, execution environment, runner

**Tool Context**:
The internal runtime parameters injected into a tool handler at execution time and hidden from model schemas.
_Avoid_: Tool state, execution payload

### Delegation & Multi-Agent

**Sub-Agent**:
A scoped, delegated agent execution instance that performs tasks and communicates with a parent agent.
_Avoid_: Child agent, slave agent, worker

**Sub-Session**:
A durable, append-only session log recorded under `subsessions/` dedicated to a sub-agent's execution history.
_Avoid_: Child thread, sub-log, child session

**Sub-Agent Triad**:
The three standardized marketplace tools (`invoke_subagent`, `send_message`, `manage_subagents`) for conversational sub-agent delegation.
_Avoid_: Child toolset, delegation api

### Interception & Transformations

**Guard**:
A plugin that intercepts turns or messages via Anima event waterfalls to enforce boundaries, safety, or token limits.
_Avoid_: Middleware, filter, interceptor

**Compaction Guard**:
A guard plugin that monitors token pressure and triggers conversational history summarization at balanced cut points.
_Avoid_: Pruning plugin, context reducer

**Truncation**:
The deterministic clipping of oversized prompt context or tool output text to protect token budgets.
_Avoid_: Compaction, pruning, slicing

**Deliberation**:
Raw reasoning or thought-chain text emitted by reasoning models prior to user-visible response tokens.
_Avoid_: Thinking process, internal monologue, reasoning trace

**Model Slug**:
A standardized model identifier formatted with a namespace prefix and model name, e.g. `openrouter/auto`.
_Avoid_: Model tag, model string, model ID
