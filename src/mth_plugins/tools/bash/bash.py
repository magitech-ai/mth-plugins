"""Bash tool handler for subprocess command execution."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


async def handle_bash(args: dict[str, Any]) -> str:
    """Executes a shell command in a subprocess and returns the output.

    Args:
        args: Dictionary containing 'command' and optional 'timeout_ms' and 'cwd'.

    Returns:
        Formatted stdout or error output string.
    """
    command = args.get("command")
    if not command:
        return "Error: 'command' argument is required."

    timeout_ms = args.get("timeout_ms", 30000)
    timeout_seconds = max(1, timeout_ms / 1000)

    cwd_str = args.get("cwd")
    cwd = Path(cwd_str) if cwd_str else None
    if cwd and not cwd.is_dir():
        return f"Error: Working directory does not exist: {cwd_str}"

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
    except TimeoutError:
        try:
            proc.kill()
        except OSError:
            pass
        return f"Command timed out after {timeout_seconds} seconds."

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode == 0:
        return stdout if stdout else "(Command executed with no output)"

    output_body = stderr or stdout or "No output produced"
    return f"Command failed with exit code {proc.returncode}:\n{output_body}"
