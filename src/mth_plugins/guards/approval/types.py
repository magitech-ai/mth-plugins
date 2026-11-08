"""Types and data structures for the approval guardrail."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from magitech_harness.approval.service import ApprovalRequest


class ApprovalOutcome(StrEnum):
    """The outcome verdict of an approval evaluation."""

    ALLOW = "allow"
    DENY = "deny"


class ApprovalScope(StrEnum):
    """The temporal scope of an approval grant."""

    ONCE = "once"
    SESSION = "session"
    PROJECT = "project"


class ApprovalReasonCode(StrEnum):
    """Reason code explaining an approval outcome."""

    RULE = "rule"
    USER = "user"
    READ_ONLY = "read_only"
    FAILURE = "failure"


@dataclass(frozen=True)
class ApprovalDecision:
    """The immutable decision verdict for an ApprovalRequest."""

    outcome: ApprovalOutcome
    scope: ApprovalScope = ApprovalScope.ONCE
    reason_code: ApprovalReasonCode = ApprovalReasonCode.RULE
    request_digest: str = ""


@dataclass(frozen=True)
class PolicyRule:
    """A declarative rule matching tool invocations."""

    tool_pattern: str
    outcome: ApprovalOutcome = ApprovalOutcome.ALLOW
    argument_patterns: dict[str, str] = field(default_factory=dict)


ApprovalPresenter = Callable[["ApprovalRequest"], Awaitable[ApprovalDecision]]
