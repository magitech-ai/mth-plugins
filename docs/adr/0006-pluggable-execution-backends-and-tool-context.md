# 0006. Pluggable Execution Backends and Tool Context Isolation

Date: 2026-11-07
Status: accepted

## Context

Domain tools such as shell execution (`bash-tool`) and filesystem manipulation (`read-file-tool`, `write-file-tool`, `edit-file-tool`) execute directly against host operating system primitives. Hardcoding ambient host OS access inside tool handlers introduces security risks in untrusted workspaces, prevents running tools inside isolated containers or remote sandboxes, and complicates hermetic testing. Furthermore, passing runtime execution parameters (such as cancellation signals, working directories, or execution backends) can leak internal implementation details into model-facing JSON schemas.

## Decision

We establish execution backend abstraction and tool context isolation for all marketplace tools:
1. **`ExecutionBackend` Abstraction**: Tools interact with the execution environment through an abstract backend interface (`run(command, ...)` and filesystem operations). The default backend executes on the local host, while alternate implementations (Docker containers, remote micro-VMs, or sandboxed environments) can be bound to context.
2. **Context Parameter Injection without Schema Leakage**: When authoring tools, parameters representing runtime execution context (such as `ToolContext`, `AbortSignal`, or `AnimaContext`) are excluded from the model-visible JSON Schema parameters and injected dynamically by the runner at call time.
3. **Privilege Budgets Over Wish Lists**: Sandboxed tools enforce security budgets at configuration time (e.g. validating module allow-lists and rejecting dangerous imports up front) rather than relying on permissive runtime attribute filters.

## Consequences

- Marketplace tools can run transparently across host environments, Docker containers, and remote sandboxes without code changes.
- Language models see clean, concise parameter schemas without internal runtime context pollution.
- Tools enforce strict filesystem bounds and execution constraints per profile.
