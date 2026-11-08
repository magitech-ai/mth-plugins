"""Unit test for truncation guardrail package exports."""

import mth_plugins.guards.truncation as pkg


def test_package_exports() -> None:
    """Verifies that truncation package exports expected symbols."""
    assert hasattr(pkg, "apply")
    assert hasattr(pkg, "truncate_head")
    assert hasattr(pkg, "truncate_tail")
    assert hasattr(pkg, "format_size")
    assert hasattr(pkg, "TruncationResult")
