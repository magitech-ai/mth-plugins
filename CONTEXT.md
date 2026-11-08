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

**Service Dependency**:
A required capability contract declared by a plugin via `inject` and `requires_services`, decoupled from concrete vendor package IDs.
_Avoid_: Plugin requirement, package import

**CodeAct**:
Direct execution of model-synthesized Python snippets with AST write-protection for registered tools, auto-`await` dispatching, and persistent session locals.
_Avoid_: Python tool, eval script, REPL runner

### Security & Human-in-the-Loop

**Approval Policy**:
A declarative TOML document (`policy.toml`) in global or workspace layers mapping tool identifiers and argument regex patterns to `allow` or `deny` outcomes.
_Avoid_: Permission list, authorization config

**Approval Request**:
An immutable question containing engine-derived tool identity, normalized arguments, and a cryptographic argument digest (`sha256:...`).
_Avoid_: Permission prompt, authorization ticket

**Approval Decision**:
An immutable verdict bound by cryptographic argument digest carrying an outcome (`allow`, `deny`), reason code (`rule`, `user`, `read_only`, `failure`), and grant scope (`once`, `session`, `project`).
_Avoid_: User confirmation, auth response

**Approval Scope**:
The temporal lifetime of an authorization: `once` for single-shot execution, `session` for the active conversation, or `project` persisted to workspace policy.
_Avoid_: Grant duration, timeout

### Diagnostics & Observability

**Language Server Bridge**:
A background JSON-RPC 2.0 stdio client translating file mutations (`edit`, `write`) into debounced compiler diagnostics and providing semantic definition/reference lookup.
_Avoid_: Linter plugin, compiler checker

**Distributed Tracing Bridge**:
An OpenTelemetry instrumentation layer capturing turn lifecycles, provider requests, and tool executions as hierarchical trace spans.
_Avoid_: Logging plugin, APM hook

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

### Session Persistence & Versioning

**Session Index**:
A SQLite full-text search database indexing conversations and messages from session JSONL event logs.
_Avoid_: Message catalog, chat index, search cache

**Session Title**:
An autonomous titling service combining heuristic fallbacks with background LLM summarization.
_Avoid_: Auto namer, session header, conversation label

**Shadow Git Repository**:
A bare Git repository isolated under user cache that tracks turn snapshots without touching primary Git tracking.
_Avoid_: Hidden repo, secondary git, backup repo

**Alternates Object Sharing**:
A Git storage optimization linking a shadow repository to primary Git objects via `objects/info/alternates`.
_Avoid_: Object symlink, shared blob pool

**Turn Snapshot**:
An immutable Git tree object hash representing the exact workspace filesystem state at a turn completion.
_Avoid_: Checkpoint commit, file backup, disk dump
