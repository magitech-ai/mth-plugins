# ADR 0009: Model Context Protocol Client Bridge

## Status
Accepted

## Date
2026-11-08

## Context
The Model Context Protocol (MCP) has emerged as an open standard for connecting AI agent hosts to external tool providers, data sources, and services. To leverage the growing ecosystem of third-party MCP servers, Magitech must provide a client bridge that discovers, connects, and dynamically exposes external tools to the execution engine.

## Decision
1. **Multi-Transport JSON-RPC 2.0 Client**:
   Implement a lightweight, zero-external-dependency JSON-RPC 2.0 protocol layer supporting both `stdio` (subprocess standard input/output) and `sse` (Server-Sent Events with HTTP POST) transports.

2. **Layer-Aware Server Discovery**:
   Discover server configurations by querying `mcp.json` across active `.agents` hierarchy layers via `ctx.layers.find_all("mcp.json")`, respecting precedence order.

3. **Namespaced Tool Mounting**:
   Map advertised MCP tools dynamically into `magitech_harness.tools.definition.Tool` instances mounted on `ctx.tools`, with namespacing formatted as `mcp_{server_name}_{tool_name}` to eliminate collision risk across multiple upstream servers.

4. **Lifecycle Disposers**:
   Tie client subprocess lifecycles and tool registrations directly to Anima context disposers (`ctx.effect`), ensuring graceful process termination and clean unregistration on context tear-down.

## Consequences
- **Positive**: Seamlessly bridges hundreds of external MCP servers into Magitech agents with zero changes to core harness logic.
- **Positive**: Automatic namespace prefixing prevents silent collisions between overlapping tool names across disparate vendors.
