"""Unit test for bash tool package exports."""

import mth_plugins.tools.bash as pkg


def test_package_exports() -> None:
    """Verifies that bash package exports expected symbols."""
    assert hasattr(pkg, "handle_bash")
    assert hasattr(pkg, "apply")
