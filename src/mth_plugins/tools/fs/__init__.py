"""Filesystem tools plugin package."""

from mth_plugins.tools.fs.fs import (
    handle_edit_file,
    handle_read_file,
    handle_write_file,
)
from mth_plugins.tools.fs.plugin import apply

__all__ = [
    "apply",
    "handle_edit_file",
    "handle_read_file",
    "handle_write_file",
]
