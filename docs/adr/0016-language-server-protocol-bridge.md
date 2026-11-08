# ADR 0016: Language Server Protocol Bridge

## Status
Accepted

## Date
2026-11-08

## Context
Coding agents frequently introduce syntax errors, broken imports, or type discrepancies when making file edits. Discovering these issues only when a full test suite is run (or not at all if tests are absent) wastes context window tokens and model iterations.

Modern language servers (e.g. `pyright`, `typescript-language-server`, `rust-analyzer`, `gopls`) provide immediate compiler and diagnostic feedback over the Language Server Protocol (LSP).

## Decision
1. **Dual Interaction Model**:
   - **Passive Post-Edit Diagnostics Hook**: The bridge listens to post-edit events on `edit` and `write` tool executions. It sends `textDocument/didChange` or `textDocument/didOpen` notifications to the corresponding language server, debounces incoming diagnostics for 150ms (up to a 3000ms deadline), and appends a structured `<diagnostics>` block directly to the tool's execution result.
   - **Active Navigation Tools**: The bridge exports callable tools (`lsp_definition`, `lsp_references`) allowing the model to jump to symbol definitions or find references across the workspace.
2. **Multi-Language Stdio Transport**:
   Maintain an asynchronous stdio JSON-RPC 2.0 client managing language server subprocesses by file extension (`.py`, `.ts`, `.rs`, `.go`, etc.). Language servers are discovered on the host `PATH` dynamically. If no server is available for a language, operations degrade gracefully without failing the edit.
3. **Bounded Diagnostic Formatting**:
   Format diagnostics as concise error and warning lines (`ERROR [line:col] message`), filtering out noisy style info to prevent token bloat.

## Consequences
- **Positive**: Immediate feedback loop on edits enables agents to self-correct compiler errors before running code.
- **Positive**: Active navigation tools enable fast, precise codebase exploration without relying solely on regex grep.
- **Positive**: Zero mandatory external daemon requirements; servers run on-demand via standard stdio.
