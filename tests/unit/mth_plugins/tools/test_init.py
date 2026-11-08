"""Unit test for tools packages exports."""

import mth_plugins.tools.bash as bash_pkg
import mth_plugins.tools.codeact as codeact_pkg
import mth_plugins.tools.edit_file as edit_pkg
import mth_plugins.tools.read_file as read_pkg
import mth_plugins.tools.write_file as write_pkg


def test_package_exports() -> None:
    """Verifies that tool packages export expected symbols."""
    assert hasattr(codeact_pkg, "CodeActExecutor")
    assert hasattr(codeact_pkg, "apply")

    assert hasattr(bash_pkg, "handle_bash")
    assert hasattr(bash_pkg, "apply")

    assert hasattr(read_pkg, "handle_read_file")
    assert hasattr(read_pkg, "apply")

    assert hasattr(write_pkg, "handle_write_file")
    assert hasattr(write_pkg, "apply")

    assert hasattr(edit_pkg, "handle_edit_file")
    assert hasattr(edit_pkg, "apply")
