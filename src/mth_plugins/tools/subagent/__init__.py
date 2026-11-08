"""Subagent orchestration tool plugin package."""

from mth_plugins.tools.subagent.manager import SubagentManager
from mth_plugins.tools.subagent.plugin import apply
from mth_plugins.tools.subagent.types import (
    RESEARCH_PRESET_TOOLS,
    SubagentRecord,
    SubagentSpec,
    SubagentState,
)

__all__ = [
    "RESEARCH_PRESET_TOOLS",
    "SubagentManager",
    "SubagentRecord",
    "SubagentSpec",
    "SubagentState",
    "apply",
]
