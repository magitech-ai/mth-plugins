# 0018. In-Process Subagent Delegation and Workspace Isolation

Date: 2026-11-08
Status: accepted

## Context

Complex software engineering workflows require delegating focused objectives to specialized sub-agents (e.g. read-only codebase exploration, unit test reproduction, or dependency audits). These tasks require:
1. Complete isolation of conversational context to avoid polluting the parent turn history.
2. Controlled workspace isolation (`inherit` vs. detached `branch` git worktrees).
3. Tool access boundaries (e.g. read-only toolsets for research subagents).
4. Cooperative cancellation propagation when parent turns abort.

## Decision

We implement `subagent-plugin` in `mth-plugins`:
1. **SubagentManager**:
   - Manages subagent instances running in-process via child `Context` and child `AgentLoopService`.
   - Records child execution transcripts into separate subsession logs (`~/.agents/sessions/subsessions/<id>.jsonl`).
   - Propagates cancellation by linking child `AbortSignal` listeners to parent abort controllers.
2. **Workspace Isolation**:
   - `inherit`: Shares parent workspace directory without git worktree overhead.
   - `branch`: Provisions an isolated git worktree via `git worktree add --detach <path> HEAD`, safely tearing it down when the subagent is killed or cleaned up.
3. **Tool Restriction Presets**:
   - `research`: Automatically limits available tools to non-mutating primitives (`read_file`, `list_files`, `find`, `grep`, `read_url`, `search_web`, `lsp_definition`, `lsp_references`).
   - `self`: Inherits the full parent tool suite.
4. **Tool Triad**:
   - `invoke_subagent`: Spawns and executes subagents with configurable wait/background behavior.
   - `send_message`: Sends conversational follow-up turns to warm subagents.
   - `manage_subagents`: Inspects live subagent state or terminates running instances.

## Consequences

- Subagents run safely and asynchronously with deterministic session transcripts.
- Workspaces remain clean and protected against concurrent file mutation when using `branch` mode.
- Preserves zero external process requirements by executing subagents within the harness runtime.
