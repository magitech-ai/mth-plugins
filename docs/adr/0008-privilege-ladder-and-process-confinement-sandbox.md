# ADR 0008: Privilege Ladder and Process Confinement Sandbox

## Status
Accepted

## Date
2026-11-08

## Context
AI agents executing arbitrary shell commands and developer tools present acute security and operational risks, including accidental system mutation, untrusted outbound network requests, and namespace contamination.

A containment mechanism is required that enforces strict isolation boundaries based on a declarative privilege budget, without compromising tool utility or coupling domain logic directly to host-specific container engines.

## Decision
1. **Privilege Budget Ladder**:
   Define four discrete containment budgets arranged in strictly ascending capability order:
   - `READONLY`: Read-only system mounts, read-only working directory, isolated tmpfs, procfs, devfs, and unshared namespaces (network, IPC, PID, UTS, cgroups).
   - `STRICT`: Read-only system mounts (`/usr`, `/bin`, `/lib`, `/lib64`), read-write working directory bind, tmpfs `/tmp`, and unshared namespaces.
   - `NETWORK`: Same filesystem containment as `STRICT`, but permits outbound network communication with DNS (`/etc/resolv.conf`) and SSL certificates (`/etc/ssl`, `/etc/pki`) mounted read-only.
   - `UNRESTRICTED`: Pass-through direct host execution without containment wrapping.

2. **Containment Engine**:
   On Linux systems, execution is encapsulated using Bubblewrap (`bwrap`) with `--die-with-parent` and unshared namespaces. Non-Linux platforms or environments lacking `bwrap` enforce fail-closed security when configured in strict enforcement mode (`enforce=True`), or emit diagnostic warnings when non-enforced.

3. **Seam Decoupling via SandboxService**:
   Expose `SandboxService` mounted on `ctx.sandbox` as a marketplace plugin (`sandbox-ladder`), keeping `magitech-harness` free of direct container toolchain bindings while providing wrapping and execution APIs to domain tools.

## Consequences
- **Positive**: Hardens subprocess execution against unintended host modification and credential exfiltration.
- **Positive**: Adheres to the principle of least privilege through verifiable privilege budgets.
- **Positive**: Maintains architectural seams with zero domain tools in the execution engine.
