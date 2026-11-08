"""Unit test for guard packages exports."""

import mth_plugins.guards.approval as approval_pkg
import mth_plugins.guards.compaction as compaction_pkg
import mth_plugins.guards.truncation as truncation_pkg


def test_package_exports() -> None:
    """Verifies that truncation and compaction packages export expected symbols."""
    assert hasattr(approval_pkg, "apply")
    assert hasattr(approval_pkg, "ApprovalGuard")
    assert hasattr(approval_pkg, "ApprovalPolicy")

    assert hasattr(truncation_pkg, "apply")
    assert hasattr(truncation_pkg, "truncate_head")
    assert hasattr(truncation_pkg, "truncate_tail")
    assert hasattr(truncation_pkg, "format_size")
    assert hasattr(truncation_pkg, "TruncationResult")

    assert hasattr(compaction_pkg, "apply")
    assert hasattr(compaction_pkg, "compact_session")
    assert hasattr(compaction_pkg, "estimate_tokens")
    assert hasattr(compaction_pkg, "estimate_history_tokens")
    assert hasattr(compaction_pkg, "find_safe_cut_index")
    assert hasattr(compaction_pkg, "summarize_events")
