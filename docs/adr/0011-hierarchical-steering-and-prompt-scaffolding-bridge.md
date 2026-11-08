# ADR 0011: Hierarchical Steering and Prompt Scaffolding Bridge

## Status
Accepted

## Date
2026-11-08

## Context
AI agents must align with layered instructions spanning organizational policies, developer preferences, persona guidelines, and project-specific architecture rules.

These instructions frequently exist in `AGENTS.md`, `CLAUDE.md`, or `.agents.md` files scattered across multiple filesystem layers.

## Decision
1. **Multi-Tier Candidate Discovery**:
   Inspect active configuration layers resolved by `LayerResolutionService` (`global -> user -> agent -> project`). In each active layer, search for candidate steering documents in precedence order: `AGENTS.md`, `CLAUDE.md`, `.agents.md`.

2. **Framed Hierarchical Assembly**:
   Assemble discovered documents in base-to-highest precedence order under framed markdown sections:
   - `## Global Policy Guidelines`
   - `## User Preferences & Defaults`
   - `## Agent Persona & Specialization`
   - `## Project Guidelines & Architecture`

3. **Dynamic Scaffolding Injection**:
   Inject the assembled steering guidelines into Layer 2 of the prompt scaffolding via `ctx.system_prompt.register_section("steering_guidelines", ...)` with automatic disposer cleanup.

## Consequences
- **Positive**: Guarantees consistent policy enforcement across the entire configuration hierarchy without manual prompt duplication.
- **Positive**: Automatically respects project isolation boundaries, ensuring project instructions never bleed into ambient sessions.
