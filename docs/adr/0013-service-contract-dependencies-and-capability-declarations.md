# ADR 0013: Service-Contract Dependencies and Capability Declarations

## Status
Accepted

## Date
2026-11-08

## Context
Plugins frequently rely on runtime capabilities provided by other plugins or the host harness. For example, `codeact-tool` requires sandboxed process containment, which may be provided by `sandbox-ladder` or an alternative containerized backend.

Hard-coupling plugins by concrete package names (`requires_plugins = ["sandbox-ladder"]`) creates vendor lock-in, prevents drop-in replacements, and leads to brittle dependency graphs. Conversely, omitting dependency declarations allows plugins to fail at runtime with obscure missing-service exceptions.

## Decision
1. **Service-Contract Declaration via `requires_services`**:
   In `PluginManifest`, introduce `requires_services: list[str]` to declare abstract service contracts (e.g. `["sandbox"]`, `["approvals"]`). A plugin's Anima fiber declares matching `inject = ["sandbox"]`.
2. **Lifecycle Coordination via Anima Fibers**:
   Anima's fiber scheduler automatically places plugins in `FiberState.PENDING` until all injected services are registered in the Context. Once the required service is mounted, the pending plugin fiber is awakened and initialized.
3. **Advisory Auto-Installation Hints via `recommended_plugins`**:
   Add `recommended_plugins: list[str]` to `PluginManifest`. Marketplace catalog resolvers and CLI bootstrapping profiles can use this hint to automatically pull and install a recommended implementation package (e.g. recommending `sandbox-ladder` for the `sandbox` contract) without hardcoding it in the plugin code.

## Consequences
- **Positive**: Clean seam between capability contracts and concrete provider packages.
- **Positive**: Seamless hot-plugging and replacement of underlying engines (e.g. replacing Bubblewrap with Docker or gVisor without changing tool plugins).
- **Positive**: Guarantees initialization order without complex topological sort passes in user code.
