"""Unit test for tools packages exports."""

import mth_plugins.tools.bash as bash_pkg
import mth_plugins.tools.fs as fs_pkg


def test_package_exports() -> None:
    """Verifies that tool packages export expected symbols."""
    assert hasattr(bash_pkg, "handle_bash")
    assert hasattr(bash_pkg, "apply")

    assert hasattr(fs_pkg, "handle_read_file")
    assert hasattr(fs_pkg, "handle_write_file")
    assert hasattr(fs_pkg, "handle_edit_file")
    assert hasattr(fs_pkg, "apply")
