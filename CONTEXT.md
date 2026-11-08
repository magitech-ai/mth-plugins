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

**Guard**:
A plugin that intercepts turns or messages via Anima event waterfalls to enforce boundaries, safety, or token limits.
_Avoid_: Middleware, filter, interceptor

### Interception & Transformations

**Compaction Guard**:
A guard plugin that monitors token pressure and triggers conversational history summarization at balanced cut points.
_Avoid_: Pruning plugin, context reducer

**Truncation**:
The deterministic clipping of oversized prompt context or tool output text to protect token budgets.
_Avoid_: Compaction, pruning, slicing
