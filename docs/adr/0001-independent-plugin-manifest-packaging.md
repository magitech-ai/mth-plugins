# 0001. Independent Plugin Manifest Packaging

Date: 2026-11-07
Status: accepted

## Context

The plugin marketplace needs to support diverse capability types (model providers, domain tools, guardrails, profiles) developed, versioned, and tested independently without tightly coupling the core harness engine to specific plugin implementations.

## Decision

We establish an explicit manifest packaging format for all marketplace plugins:
1. Every plugin is isolated in its own directory (e.g. `src/mth_plugins/providers/openrouter/`) containing a declarative `manifest.json`.
2. The manifest declares `name`, `version`, `description`, `types` (`Provider`, `Tool`, `Guard`), `author`, and `entrypoint`.
3. The entrypoint defines an `apply(ctx)` callable that mounts the plugin's capabilities directly onto the host Anima context.
4. A root `index.json` acts as the discoverable catalog, mapping plugin IDs to their manifest relative paths.

## Consequences

- Plugins are self-describing, modular, and can be individually verified and loaded by the harness plugin service.
- New plugins can be introduced into the catalog without requiring code changes to the core runtime or other plugins.
- Central discovery requires keeping `index.json` synchronized when adding or moving plugins.
