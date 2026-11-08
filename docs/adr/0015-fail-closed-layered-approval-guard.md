# ADR 0015: Fail-Closed Layered Approval Policy Guard

## Status
Accepted

## Date
2026-11-08

## Context
Autonomous agents executing arbitrary system commands or file modifications require human-in-the-loop oversight for security-critical actions. A naive confirmation prompt on every single tool call creates severe user fatigue, leading to accidental blanket approvals. Conversely, a hardcoded tool allowlist fails to distinguish between safe read commands and destructive write commands.

A flexible policy engine is required that supports declarative rules across workspace and user layers, cryptographic argument digests to prevent time-of-check to time-of-use (TOCTOU) attacks, and scoped interactive grants.

## Decision
1. **Immutable Approval Request & Digest Binding**:
   Before a tool call is executed, an `ApprovalRequest` is constructed with normalized arguments and a canonical SHA-256 argument digest (`sha256:<hex>`). Any decision returned must match the request's exact digest; mismatched digests are treated as stale and denied fail-closed.
2. **Layered Declarative Policy (`policy.toml`)**:
   Load policy definitions from global (`~/.agents/approval/policy.toml`) and project (`{project}/.agents/approval/policy.toml`) layers:
   - Rules specify tool name patterns (exact or glob/regex) and argument matching criteria (e.g. read-only path checks, command prefixes).
   - Rules yield explicit `allow` or `deny` outcomes.
3. **Interactive Presenter with Scoped Decisions**:
   When no declarative rule resolves an action, the request is delegated to an interactive UI presenter (`ApprovalPresenter`).
   The user's response carries a grant scope:
   - `ONCE`: Valid only for the single immediate execution.
   - `SESSION`: Cached in-memory for the active session and tool identifier.
   - `PROJECT`: Persisted to the project's `policy.toml` for recurring allow-listing.
4. **Fail-Closed AND Evaluation**:
   If multiple gates or guards are mounted, all must grant approval. If any handler raises an exception, cancels, times out, or returns `deny`, the execution is aborted immediately with an synthetic denial message.

## Consequences
- **Positive**: Cryptographic argument binding prevents argument mutation between display and execution.
- **Positive**: Scoped grants reduce prompt fatigue while maintaining granular security.
- **Positive**: Fail-closed architecture prevents unauthorized execution when UI presenters are disconnected.
