"""Tests for codeact tool package exports."""

import mth_plugins.tools.codeact as codeact_pkg


def test_init_exports() -> None:
    assert hasattr(codeact_pkg, "CodeActExecutor")
    assert hasattr(codeact_pkg, "ASTSafetyVisitor")
    assert hasattr(codeact_pkg, "WriteProtectionVisitor")
    assert hasattr(codeact_pkg, "CodeActTransformer")
    assert hasattr(codeact_pkg, "FinalAnswerError")
    assert hasattr(codeact_pkg, "FinalAnswerException")
    assert hasattr(codeact_pkg, "apply")
