# 0005. Sub-Agent Delegation Tools and Orchestration

Date: 2026-11-07
Status: accepted

## Context

Complex agent tasks require decomposing work across delegated sub-agents (e.g. background codebase research, isolated prototyping, or database debugging) without blocking the primary agent or polluting its context window with extensive intermediate research steps.

## Decision

We package sub-agent orchestration as a first-class plugin in `mth-plugins`:
1. **Delegation Tool Triad**: Exposes three standardized tools to language models:
   - `invoke_subagent`: Spawns a sub-agent with a defined prompt, role description, workspace mode, and model tier.
   - `send_message`: Sends conversational follow-up instructions to an existing warm sub-agent by its conversation ID.
   - `manage_subagents`: Inspects live sub-agents or terminates active instances.
2. **Execution Seam Consumption**: Consumes the `magitech-harness` sub-session persistence seam (`subsessions/<id>.jsonl`) and reactive wakeup turn queue.
3. **Workspace Isolation**: Supports workspace modes (`inherit`, `branch`, `share`), allowing sub-agents to operate in isolated worktrees or shared directory roots without file conflicts.

## Consequences

- Agents can autonomously delegate multi-step background tasks while maintaining a clean conversational context.
- Delegation capabilities are pluggable and can be enabled, customized, or restricted per profile.
- Sub-agent executions are fully attributed and auditable in persisted sub-session transcripts.
