"""Unit tests for SubagentManager orchestration, workspace isolation, and lifecycles."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anima import Context
from magitech_harness.agent.cancellation import AbortSignal
from magitech_harness.agent.loop import AgentLoopService
from magitech_harness.llm.service import LLMService
from magitech_harness.session.service import SessionService
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.subagent.manager import SubagentManager
from mth_plugins.tools.subagent.types import SubagentSpec, SubagentState


class MockLoop(AgentLoopService):
    def __init__(self, ctx: Context, return_value: str = "Turn result") -> None:
        super().__init__(ctx)
        self.return_value = return_value
        self.raise_exc: Exception | None = None

    async def run_turn(
        self,
        session: Any,
        user_input: str,
        *,
        model: str | None = None,
        max_steps: int = 10,
        signal: AbortSignal | None = None,
    ) -> str:
        if self.raise_exc:
            raise self.raise_exc
        return self.return_value


@pytest.fixture
def parent_ctx(tmp_path: Path) -> Context:
    ctx = Context()
    ctx.workspace_dir = tmp_path
    SessionService(ctx, {"base_storage_dir": tmp_path / "sessions"})
    tools = ToolService(ctx)
    tools.register(
        Tool(name="read_file", description="", parameters={}, handler=AsyncMock())
    )
    tools.register(
        Tool(name="write_file", description="", parameters={}, handler=AsyncMock())
    )
    tools.register(
        Tool(name="invoke_subagent", description="", parameters={}, handler=AsyncMock())
    )
    llm = LLMService(ctx)
    llm.default_model = "test-model"
    return ctx


@pytest.mark.asyncio
async def test_subagent_manager_invoke_sync_and_presets(
    parent_ctx: Context, tmp_path: Path
) -> None:
    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    # 1. Research preset: automatically restricts to research tools
    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=lambda c: MockLoop(c, "Research completed"),
    ):
        specs = [
            SubagentSpec(
                role="Codebase Researcher",
                prompt="Audit files",
                wait=True,
            )
        ]
        records = await manager.invoke(specs)
        assert len(records) == 1
        rec = records[0]
        assert rec.role == "Codebase Researcher"
        assert rec.state == SubagentState.COMPLETED
        assert rec.summary == "Research completed"
        assert "read_file" in rec.effective_tools
        assert "write_file" not in rec.effective_tools

    # 2. General role with custom allowed_tools
    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=lambda c: MockLoop(c, "Custom completed"),
    ):
        specs2 = [
            SubagentSpec(
                role="worker",
                prompt="Do work",
                model="custom-model",
                allowed_tools=frozenset({"write_file"}),
                wait=True,
            )
        ]
        records2 = await manager.invoke(specs2)
        rec2 = records2[0]
        assert rec2.model_id == "custom-model"
        assert rec2.effective_tools == ["write_file"]
        assert rec2.summary == "Custom completed"


@pytest.mark.asyncio
async def test_subagent_manager_invoke_background_and_send_message(
    parent_ctx: Context, tmp_path: Path
) -> None:
    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    loop_instances: list[MockLoop] = []

    def _loop_factory(c: Context) -> MockLoop:
        loop = MockLoop(c, "Turn 1 done")
        loop_instances.append(loop)
        return loop

    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=_loop_factory,
    ):
        # Background execution (wait=False)
        spec = SubagentSpec(role="assistant", prompt="Background work", wait=False)
        records = await manager.invoke([spec])
        rec = records[0]
        assert rec.subagent_id in manager._tasks

        # Await task to finish
        await manager._tasks[rec.subagent_id]
        assert rec.state == SubagentState.COMPLETED

        # Send follow-up message
        loop_instances[0].return_value = "Follow up done"
        rec_after = await manager.send_message(rec.subagent_id, "Next instruction")
        assert rec_after.summary == "Follow up done"


@pytest.mark.asyncio
async def test_subagent_manager_branch_workspace_git(
    parent_ctx: Context, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    manager = SubagentManager(
        parent_ctx,
        {
            "subsessions_dir": tmp_path / "subsessions",
            "workspace_root": tmp_path,
        },
    )

    # 1. Successful worktree creation
    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=mock_proc_ok),
        ),
        patch(
            "mth_plugins.tools.subagent.manager.AgentLoopService",
            side_effect=lambda c: MockLoop(c, "Worktree turn done"),
        ),
    ):
        spec = SubagentSpec(
            role="branch-worker",
            prompt="Work on branch",
            workspace="branch",
            wait=True,
        )
        records = await manager.invoke([spec])
        rec = records[0]
        assert "worktrees" in str(rec.workspace_path)
        assert rec.subagent_id in manager._worktrees

        # Test manage kill cleans up worktree
        mock_rm_proc = MagicMock()
        mock_rm_proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=mock_rm_proc),
        ):
            killed = await manager.manage("kill", [rec.subagent_id])
            assert len(killed) == 1
            assert killed[0].state == SubagentState.TERMINATED
            assert rec.subagent_id not in manager._worktrees

    # 2. Branch workspace when not a git repo -> falls back to workspace_root
    non_git_ws = tmp_path / "nongit"
    non_git_ws.mkdir()
    manager_nongit = SubagentManager(
        parent_ctx,
        {
            "subsessions_dir": tmp_path / "subsessions",
            "workspace_root": non_git_ws,
        },
    )
    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=lambda c: MockLoop(c, "Done"),
    ):
        spec2 = SubagentSpec(role="w", prompt="", workspace="branch", wait=True)
        recs2 = await manager_nongit.invoke([spec2])
        assert recs2[0].workspace_path == non_git_ws

    # 3. Branch workspace when git command raises OSError
    with (
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("git not found"),
        ),
        patch(
            "mth_plugins.tools.subagent.manager.AgentLoopService",
            side_effect=lambda c: MockLoop(c, "Done"),
        ),
    ):
        recs3 = await manager.invoke(
            [SubagentSpec(role="w", prompt="", workspace="branch", wait=True)]
        )
        assert recs3[0].workspace_path == tmp_path

    # 4. Branch workspace when git returncode != 0
    mock_proc_fail = MagicMock()
    mock_proc_fail.returncode = 1
    mock_proc_fail.communicate = AsyncMock(return_value=(b"", b"fatal: git error"))
    with (
        patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=mock_proc_fail),
        ),
        patch(
            "mth_plugins.tools.subagent.manager.AgentLoopService",
            side_effect=lambda c: MockLoop(c, "Done"),
        ),
    ):
        recs4 = await manager.invoke(
            [SubagentSpec(role="w", prompt="", workspace="branch", wait=True)]
        )
        assert recs4[0].workspace_path == tmp_path


@pytest.mark.asyncio
async def test_subagent_manager_manage_and_errors(
    parent_ctx: Context, tmp_path: Path
) -> None:
    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    # 1. Send message to nonexistent subagent
    with pytest.raises(ValueError, match="does not exist"):
        await manager.send_message("nonexistent", "hello")

    # 2. Turn execution failure in child loop
    def _failing_loop_factory(c: Context) -> MockLoop:
        loop = MockLoop(c)
        loop.raise_exc = RuntimeError("Execution crashed")
        return loop

    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=_failing_loop_factory,
    ):
        spec = SubagentSpec(role="failing", prompt="crash me", wait=True)
        recs = await manager.invoke([spec])
        assert recs[0].state == SubagentState.ERRORED
        assert "Execution crashed" in (recs[0].error or "")

    # 3. Session missing error in child context
    sid = recs[0].subagent_id
    child_ctx = manager._child_contexts[sid]
    child_ctx.sessions._active_sessions.clear()
    await manager._run_child(sid, "another prompt")
    assert recs[0].state == SubagentState.ERRORED
    assert "not found in child context" in (recs[0].error or "")

    # 4. Manage list and kill_all
    active = await manager.manage("list")
    assert len(active) >= 1

    # Kill with non-existent sid in list
    res_kill = await manager.manage("kill", ["nonexistent_id", sid])
    assert len(res_kill) == 1

    all_killed = await manager.manage("kill_all")
    assert all(r.state == SubagentState.TERMINATED for r in all_killed)

    # 5. Send message to terminated subagent
    with pytest.raises(ValueError, match="terminated"):
        await manager.send_message(sid, "hello")

    # 6. Unknown manage action
    with pytest.raises(ValueError, match="Unknown manage_subagents action"):
        await manager.manage("invalid_action")

    # 7. Shutdown calls kill_all
    await manager.shutdown()


@pytest.mark.asyncio
async def test_subagent_cancellation_cascade(
    parent_ctx: Context, tmp_path: Path
) -> None:
    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    parent_signal = AbortSignal()
    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=lambda c: MockLoop(c, "Done"),
    ):
        recs = await manager.invoke(
            [SubagentSpec(role="w", prompt="test", wait=True)],
            parent_signal=parent_signal,
        )
        child_signal = manager._signals[recs[0].subagent_id]
        assert not child_signal.is_aborted

        parent_signal.abort("Parent aborted")
        assert child_signal.is_aborted
        assert child_signal.reason == "Parent aborted"


@pytest.mark.asyncio
async def test_subagent_empty_context_and_worktree_cleanup_failure(
    tmp_path: Path,
) -> None:
    empty_ctx = Context()
    manager = SubagentManager(empty_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    with patch(
        "mth_plugins.tools.subagent.manager.AgentLoopService",
        side_effect=lambda c: MockLoop(c, "Done"),
    ):
        recs = await manager.invoke(
            [SubagentSpec(role="no_tools", prompt="", wait=True)]
        )
        assert recs[0].effective_tools == []

    # Test worktree removal failure in _terminate_child
    sid = recs[0].subagent_id
    manager._worktrees[sid] = tmp_path / "fake_wt"
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("rm failed")):
        await manager._terminate_child(sid)
        assert sid not in manager._worktrees


@pytest.mark.asyncio
async def test_subagent_terminate_running_task_and_missing_record(
    parent_ctx: Context, tmp_path: Path
) -> None:
    manager = SubagentManager(parent_ctx, {"subsessions_dir": tmp_path / "subsessions"})

    # Background task that sleeps
    async def _long_turn(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(_long_turn())
    manager._tasks["sub-sleep"] = task

    await manager._terminate_child("sub-sleep")
    assert task.cancelled()

    # Already completed task
    async def _instant() -> None:
        pass

    done_task = asyncio.create_task(_instant())
    await done_task
    manager._tasks["sub-done"] = done_task
    await manager._terminate_child("sub-done")

    # Terminate child where sid has no record and no signal
    await manager._terminate_child("nonexistent")
