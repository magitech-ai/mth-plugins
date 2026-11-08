"""Declarative TOML policy engine for the approval guardrail."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mth_plugins.guards.approval.types import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalScope,
    PolicyRule,
)

if TYPE_CHECKING:
    from magitech_harness.approval.service import ApprovalRequest


class ApprovalPolicy:
    """Manages parsing and evaluation of declarative policy rules."""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self.rules: list[PolicyRule] = rules or []

    @classmethod
    def load(cls, path: Path) -> ApprovalPolicy:
        """Loads policy rules from a policy.toml file."""
        if not path.is_file():
            return cls([])

        try:
            content = path.read_text(encoding="utf-8")
            data = tomllib.loads(content)
        except Exception:
            return cls([])

        rules: list[PolicyRule] = []
        raw_rules = data.get("rules", [])
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if not isinstance(item, dict):
                    continue
                tool = item.get("tool")
                if not isinstance(tool, str):
                    continue
                raw_outcome = item.get("outcome", "allow")
                outcome = (
                    ApprovalOutcome.DENY
                    if str(raw_outcome).lower() == "deny"
                    else ApprovalOutcome.ALLOW
                )
                args = item.get("arguments", {})
                arg_patterns = (
                    {str(k): str(v) for k, v in args.items()}
                    if isinstance(args, dict)
                    else {}
                )
                rules.append(
                    PolicyRule(
                        tool_pattern=tool,
                        outcome=outcome,
                        argument_patterns=arg_patterns,
                    )
                )

        return cls(rules)

    def evaluate(self, request: ApprovalRequest) -> ApprovalDecision | None:
        """Evaluates an ApprovalRequest against policy rules in order.

        Returns an ApprovalDecision if a matching rule is found, or None.
        """
        for rule in self.rules:
            # Match tool name (supports exact match and glob like 'fs_*' or '*')
            if not fnmatch.fnmatch(request.tool_name, rule.tool_pattern):
                continue

            # Match argument patterns if any
            matched_args = True
            for arg_key, pattern in rule.argument_patterns.items():
                if arg_key not in request.arguments:
                    matched_args = False
                    break
                val_str = str(request.arguments[arg_key])
                try:
                    if not re.search(pattern, val_str):
                        matched_args = False
                        break
                except re.error:
                    matched_args = False
                    break

            if matched_args:
                return ApprovalDecision(
                    outcome=rule.outcome,
                    scope=ApprovalScope.PROJECT,
                    reason_code=ApprovalReasonCode.RULE,
                    request_digest=request.digest,
                )

        return None

    def save_rule(self, path: Path, rule: PolicyRule) -> None:
        """Appends a rule to the specified policy.toml file."""
        self.rules.append(rule)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = [
            "\n[[rules]]",
            f'tool = "{rule.tool_pattern}"',
            f'outcome = "{rule.outcome.value}"',
        ]
        if rule.argument_patterns:
            lines.append("[rules.arguments]")
            for k, v in sorted(rule.argument_patterns.items()):
                escaped_v = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{escaped_v}"')
        lines.append("")

        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
