# ADR 0012: Workspace Trust Gate and Integrity Verification

## Status
Accepted

## Date
2026-11-08

## Context
When an AI agent opens an untrusted repository or workspace, project-defined configuration files (e.g. `{project}/.agents/mcp.json`, project skills, custom plugins) could execute arbitrary shell commands or launch malicious local servers.

A cryptographically verifiable trust verification mechanism is essential before loading or executing any project-tier extensions.

## Decision
1. **Deterministic SHA-256 Directory Tree Hashing**:
   Implement `compute_directory_tree_hash(dir_path: Path)` which deterministically traverses all non-ignored files, sorting them by relative POSIX path and feeding their relative paths, sizes, and file bytes into a rolling SHA-256 digest.

2. **Durable Trust Store (`TrustStore`)**:
   Persist workspace trust verdicts to `~/.agents/approval/trust.json` using atomic temporary file replacements (`.tmp` + `replace`). Support three active verdict states:
   - `TRUST_EXACT`: Trusted for this specific tree hash. If files in `.agents/` are modified, the hash changes and trust resets to `UNSPECIFIED`.
   - `TRUST_PARENT`: Entire parent directory prefix (e.g. developer workspace root) is trusted.
   - `DECLINE`: Explicitly declined workspace.

3. **Fail-Closed Gate Enforcement**:
   - Workspaces lacking a project `.agents/` directory are trusted by default (no executable code).
   - If a project defines `.agents/` and its status is `UNSPECIFIED`, request human approval via `ctx.approvals.request_approval(...)`.
   - In non-interactive environments or when no approval broker is mounted, fail closed (`return False`), preventing execution of untrusted project extensions.

## Consequences
- **Positive**: Eliminates remote code execution vectors from untrusted Git repositories containing malicious `.agents` configurations.
- **Positive**: Hash sensitivity ensures prompt re-verification whenever project configuration files are modified.
