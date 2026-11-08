"""Edit file tool plugin package."""

from mth_plugins.tools.edit_file.edit_file import handle_edit_file
from mth_plugins.tools.edit_file.plugin import apply

__all__ = [
    "apply",
    "handle_edit_file",
]
