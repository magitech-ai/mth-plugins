"""Bash tool plugin package."""

from mth_plugins.tools.bash.bash import handle_bash
from mth_plugins.tools.bash.plugin import apply

__all__ = ["apply", "handle_bash"]
