# ADR 0007: Tool Output Spilling and File Pointer Recovery

## Status
Accepted

## Date
2026-11-08

## Context
When AI agents execute shell commands or domain tools that generate massive outputs (e.g. build logs, large file searches, git diffs), two conflicting requirements arise:
1. **Context Window Preservation**: Passing hundreds of kilobytes of raw terminal output directly into model conversation history causes rapid token exhaustion, expensive inference costs, and model context degradation.
2. **Lossless Output Recovery**: The model frequently needs access to specific lines or portions of the full output to complete debugging or code repair tasks.

While the host engine (`magitech-harness`) enforces an in-memory buffer ceiling (64 KiB) to prevent host memory exhaustion, the domain tool must provide a recovery mechanism.

## Decision
1. **Automatic Spill-to-Disk on Truncation**:
   When `handle_bash` executes a command where output is truncated by the engine buffer (`res.bytes_read > max_output_bytes` or `[truncated` markers), the tool persists the full output stream to an isolated disk spill file:
   `~/.agents/spill/<uuid>.stdout` (up to a 64 MiB ceiling).
2. **Model-Facing Spill Pointers**:
   The tool result returned to the model includes the bounded head/tail summary and an explicit file pointer:
   `[Full output (X bytes) spilled to: ~/.agents/spill/<uuid>.stdout]`
3. **Progressive Inspection Workflow**:
   The model can inspect specific sections of the spilled output using `read_file` with `offset` and `limit` pagination parameters, achieving full auditability without flooding the primary context.

## Consequences
- **Positive**: Protects LLM context windows and token budgets while guaranteeing zero loss of diagnostic information.
- **Positive**: Seamlessly bridges the core engine's in-memory bounded buffer with user-accessible persistent storage.
