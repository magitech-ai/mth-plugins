"""Unit test for provider packages exports."""

import mth_plugins.providers.openrouter as openrouter_pkg
import mth_plugins.providers.pollinations as pollinations_pkg


def test_package_exports() -> None:
    """Verifies that provider packages export expected symbols."""
    assert hasattr(openrouter_pkg, "OpenRouterProvider")
    assert hasattr(openrouter_pkg, "apply")

    assert hasattr(pollinations_pkg, "PollinationsProvider")
    assert hasattr(pollinations_pkg, "apply")
    assert hasattr(pollinations_pkg, "wire_model_id")
