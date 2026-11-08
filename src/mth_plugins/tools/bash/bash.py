"""Bash tool handler for subprocess command execution and spill management."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from anima import Context

DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KiB in-memory limit


async def handle_bash(
    args: dict[str, Any],
    ctx: Context | None = None,
    spill_dir: Path | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> str:
    """Executes a shell command via ctx.shell with spill-to-disk recovery.

    Args:
        args: Dictionary containing 'command' and optional 'timeout_ms' and 'cwd'.
        ctx: Optional Anima context providing ctx.shell.
        spill_dir: Optional custom spill directory (defaults to ~/.agents/spill).
        max_output_bytes: In-memory budget before output is truncated and spilled.

    Returns:
        Formatted stdout or error output string with optional spill file pointer.
    """
    command = args.get("command")
    if not command:
        return "Error: 'command' argument is required."

    timeout_ms = args.get("timeout_ms", 30000)
    timeout_seconds = max(0.001, timeout_ms / 1000)

    cwd_str = args.get("cwd")
    cwd = Path(cwd_str) if cwd_str else None
    if cwd and not cwd.is_dir():
        return f"Error: Working directory does not exist: {cwd_str}"

    if ctx is not None and ctx.has("shell"):
        res = await ctx.shell.run(
            command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        exit_code = res.exit_code
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()
        timed_out = res.timed_out
        bytes_read = res.bytes_read
    else:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            exit_code = proc.returncode if proc.returncode is not None else -1
            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            timed_out = False
            bytes_read = len(stdout_bytes) + len(stderr_bytes)
        except TimeoutError:
            try:
                proc.kill()
            except OSError:
                pass
            return f"Command timed out after {timeout_seconds} seconds."

    if timed_out:
        return f"Command timed out after {timeout_seconds} seconds."

    spill_note = ""
    if (
        bytes_read > max_output_bytes
        or "[truncated" in stdout
        or "[truncated" in stderr
    ):
        effective_spill_dir = spill_dir or (Path.home() / ".agents" / "spill")
        try:
            effective_spill_dir.mkdir(parents=True, exist_ok=True)
            spill_id = str(uuid.uuid4())
            spill_file = effective_spill_dir / f"{spill_id}.stdout"
            spill_content = stdout + (f"\n{stderr}" if stderr else "")
            spill_file.write_text(spill_content, encoding="utf-8")
            spill_note = (
                f"\n\n[Full output ({bytes_read} bytes) spilled to: {spill_file}]"
            )
        except OSError:
            pass

    if exit_code == 0:
        base = stdout if stdout else "(Command executed with no output)"
        return base + spill_note

    output_body = stderr or stdout or "No output produced"
    return f"Command failed with exit code {exit_code}:\n{output_body}{spill_note}"
