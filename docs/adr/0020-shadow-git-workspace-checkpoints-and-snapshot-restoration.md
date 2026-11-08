# 0020. Shadow Git Workspace Checkpoints and Snapshot Restoration

Date: 2026-11-08
Status: accepted

## Context

Autonomous agents executing multiple editing turns or tool commands may produce regressions, erroneous code modifications, or undesired file deletions. Safe execution requires:
1. Low-overhead snapshots of the working tree taken before and after agent turns.
2. Fast inspection of diffs introduced across turns or checkpoints.
3. Reliable rollback and restoration of the workspace filesystem to any previous snapshot.
4. Protection against runaway disk consumption and timeout failures in large repositories.

## Decision

We implement `checkpoint-bridge` in `mth-plugins`:
1. **Shadow Bare Git Repository**:
   - Manages a bare Git repository per workspace under `~/.agents/checkpoints/<repo-hash>`.
   - Links Git object storage via `objects/info/alternates` to the workspace's `.git/objects` when available, enabling near-instantaneous snapshots with zero disk duplication for committed assets.
2. **Turn Snapshot Capture**:
   - Captures tree snapshots via a temporary index (`GIT_INDEX_FILE=... git add -A` and `git write-tree`) without modifying the workspace repository's working index or HEAD.
   - Enforces pre-scan safety bounds (`MAX_CAPTURE_FILES = 50_000`, `MAX_CAPTURE_BYTES = 1 GiB`) with `.gitignore` awareness, aborting early if the worktree exceeds bounds to prevent hanging turns.
   - Records mapping of turn identifiers and `latest` to tree object SHAs.
3. **Workspace Inspection & Restoration Tools**:
   - `checkpoint_diff`: Produces standard unified diffs between two checkpoints or between a checkpoint and the active working directory.
   - `checkpoint_restore`: Restores workspace files to a specific snapshot state by reading tree objects without modifying primary git branch history.

## Consequences

- Turns can be freely rolled back or compared without polluting user git commit logs or branches.
- Object deduplication keeps snapshot disk consumption minimal.
- Pre-scan limits guarantee predictable execution times even in large monorepos.
