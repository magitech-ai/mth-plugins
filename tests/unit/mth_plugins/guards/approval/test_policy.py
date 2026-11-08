"""Unit tests for approval policy loading and evaluation."""

from pathlib import Path

from magitech_harness.approval.service import ApprovalRequest

from mth_plugins.guards.approval.policy import ApprovalPolicy
from mth_plugins.guards.approval.types import (
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalScope,
    PolicyRule,
)


def test_load_nonexistent_policy(tmp_path: Path) -> None:
    policy = ApprovalPolicy.load(tmp_path / "missing.toml")
    assert policy.rules == []


def test_load_malformed_policy(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.toml"
    bad_file.write_text("invalid toml content [[[", encoding="utf-8")
    policy = ApprovalPolicy.load(bad_file)
    assert policy.rules == []

    # Non-list rules key
    non_list_file = tmp_path / "non_list.toml"
    non_list_file.write_text('rules = "not a list"', encoding="utf-8")
    policy_nl = ApprovalPolicy.load(non_list_file)
    assert policy_nl.rules == []

    # Non-dict item in rules list
    non_dict_item_file = tmp_path / "non_dict_item.toml"
    non_dict_item_file.write_text('rules = ["string_item"]', encoding="utf-8")
    policy_ndi = ApprovalPolicy.load(non_dict_item_file)
    assert policy_ndi.rules == []

    # Rule without valid string tool
    bad_tool_file = tmp_path / "bad_tool.toml"
    bad_tool_file.write_text(
        '[[rules]]\ntool = 123\noutcome = "allow"', encoding="utf-8"
    )
    policy_bt = ApprovalPolicy.load(bad_tool_file)
    assert policy_bt.rules == []


def test_load_and_evaluate_policy(tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.toml"
    # Note: adding an invalid rule inside a valid list to test filtering
    content_valid = """
[[rules]]
tool = "read_file"
outcome = "allow"

[[rules]]
not_dict = 123

[[rules]]
tool = "bash"
outcome = "allow"
[rules.arguments]
command = "^pytest.*"

[[rules]]
tool = "bash"
outcome = "deny"
[rules.arguments]
command = ".*rm\\\\s+-rf.*"

[[rules]]
tool = "fs_*"
outcome = "allow"
"""
    policy_file.write_text(content_valid, encoding="utf-8")
    policy = ApprovalPolicy.load(policy_file)
    assert len(policy.rules) == 4

    # 1. Exact match on read_file
    req1 = ApprovalRequest(
        tool_name="read_file",
        arguments={"path": "foo.py"},
        digest="sha256:111",
    )
    dec1 = policy.evaluate(req1)
    assert dec1 is not None
    assert dec1.outcome is ApprovalOutcome.ALLOW
    assert dec1.scope is ApprovalScope.PROJECT
    assert dec1.reason_code is ApprovalReasonCode.RULE
    assert dec1.request_digest == "sha256:111"

    # 2. Bash with pytest command -> allow
    req2 = ApprovalRequest(
        tool_name="bash",
        arguments={"command": "pytest -v"},
        digest="sha256:222",
    )
    dec2 = policy.evaluate(req2)
    assert dec2 is not None
    assert dec2.outcome is ApprovalOutcome.ALLOW

    # 3. Bash with rm -rf command -> deny
    req3 = ApprovalRequest(
        tool_name="bash",
        arguments={"command": "rm -rf /tmp/data"},
        digest="sha256:333",
    )
    dec3 = policy.evaluate(req3)
    assert dec3 is not None
    assert dec3.outcome is ApprovalOutcome.DENY

    # 4. Bash with argument missing "command"
    req_no_arg = ApprovalRequest(
        tool_name="bash",
        arguments={"cwd": "/tmp"},
        digest="sha256:444",
    )
    assert policy.evaluate(req_no_arg) is None

    # 5. Bash with non-matching command
    req_other = ApprovalRequest(
        tool_name="bash",
        arguments={"command": "ls -la"},
        digest="sha256:555",
    )
    assert policy.evaluate(req_other) is None

    # 6. Glob match on fs_*
    req_glob = ApprovalRequest(
        tool_name="fs_write",
        arguments={},
        digest="sha256:666",
    )
    dec_glob = policy.evaluate(req_glob)
    assert dec_glob is not None
    assert dec_glob.outcome is ApprovalOutcome.ALLOW

    # 7. Unmatched tool
    req_unknown = ApprovalRequest(
        tool_name="unknown_tool",
        arguments={},
        digest="sha256:777",
    )
    assert policy.evaluate(req_unknown) is None


def test_evaluate_invalid_regex(tmp_path: Path) -> None:
    rule = PolicyRule(
        tool_pattern="bash",
        outcome=ApprovalOutcome.ALLOW,
        argument_patterns={"command": "[unclosed regex"},
    )
    policy = ApprovalPolicy([rule])
    req = ApprovalRequest(
        tool_name="bash",
        arguments={"command": "echo test"},
        digest="sha256:888",
    )
    assert policy.evaluate(req) is None


def test_save_rule(tmp_path: Path) -> None:
    policy_file = tmp_path / "sub" / "policy.toml"
    policy = ApprovalPolicy()
    rule = PolicyRule(
        tool_pattern="bash",
        outcome=ApprovalOutcome.ALLOW,
        argument_patterns={"command": r'echo "hello\world"'},
    )
    policy.save_rule(policy_file, rule)

    # Re-load
    loaded = ApprovalPolicy.load(policy_file)
    assert len(loaded.rules) == 1
    assert loaded.rules[0].tool_pattern == "bash"
    assert loaded.rules[0].outcome is ApprovalOutcome.ALLOW
    assert loaded.rules[0].argument_patterns == {"command": r'echo "hello\world"'}
