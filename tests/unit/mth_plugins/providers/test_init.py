"""Unit test for openrouter provider package exports."""

import mth_plugins.providers.openrouter as pkg


def test_package_exports() -> None:
    """Verifies that openrouter package exports expected symbols."""
    assert hasattr(pkg, "OpenRouterProvider")
    assert hasattr(pkg, "apply")
