"""Unit tests for SkillsBridgeService discovery and execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from anima import Context
from magitech_harness.components.layers import ConfigLayer
from magitech_harness.session.events import ToolCallData
from magitech_harness.shell.service import ShellResult
from magitech_harness.system_prompt.service import SystemPromptService
from magitech_harness.tools.service import ToolService

from mth_plugins.bridges.skills.service import SkillsBridgeService


def _create_dummy_skill(
    base_dir: Path, name: str, script_name: str | None = None
) -> Path:
    skill_dir = base_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: Test skill {name}\n---\n"
        f"# Body for {name}\nFollow instructions."
    )

    if script_name:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file = scripts_dir / script_name
        script_file.write_text("#!/bin/sh\necho hello-from-script\n")
        script_file.chmod(0o755)

    return skill_file


async def test_skills_service_discovery_and_catalog(tmp_path: Path) -> None:
    ctx = Context()
    ctx.use(ToolService)
    ctx.use(SystemPromptService)
    await ctx.flush()

    service = SkillsBridgeService(ctx)

    # Create dummy skills
    skills_root = tmp_path / "skills"
    _create_dummy_skill(skills_root, "skill-a", script_name="run.sh")
    _create_dummy_skill(skills_root, "skill-b")

    discovered = service.discover_skills(explicit_dir=skills_root)
    assert "skill-a" in discovered
    assert "skill-b" in discovered
    assert len(service.skills) == 2

    # Check XML catalog rendered into ctx.system_prompt
    rendered_prompt = await ctx.system_prompt.render()
    assert "<skills>" in rendered_prompt
    assert "<name>skill-a</name>" in rendered_prompt
    assert "<name>skill-b</name>" in rendered_prompt


async def test_skills_service_activate_tool(tmp_path: Path) -> None:
    ctx = Context()
    ctx.use(ToolService)
    await ctx.flush()

    service = SkillsBridgeService(ctx)
    skills_root = tmp_path / "skills"
    _create_dummy_skill(skills_root, "code-helper")
    service.discover_skills(explicit_dir=skills_root)

    assert ctx.tools.get("activate_skill") is not None

    # Call activate_skill for existing skill
    res = await ctx.tools.execute(
        ToolCallData(
            call_id="call-1",
            name="activate_skill",
            arguments={"name": "code-helper"},
        )
    )
    assert "# Skill: code-helper" in res.content
    assert "Follow instructions." in res.content

    # Call activate_skill for non-existent skill
    err_res = await ctx.tools.execute(
        ToolCallData(
            call_id="call-2",
            name="activate_skill",
            arguments={"name": "non-existent"},
        )
    )
    assert "Error: Skill 'non-existent' not found" in err_res.content


async def test_skills_service_run_script_tool(tmp_path: Path) -> None:
    ctx = Context()
    ctx.use(ToolService)
    await ctx.flush()

    service = SkillsBridgeService(ctx)
    skills_root = tmp_path / "skills"
    _create_dummy_skill(skills_root, "runner", script_name="test.sh")
    service.discover_skills(explicit_dir=skills_root)

    # 1. Non-existent skill
    res_no_skill = await ctx.tools.execute(
        ToolCallData(
            call_id="c1",
            name="run_skill_script",
            arguments={"skill_name": "missing", "script_name": "test.sh"},
        )
    )
    assert "Error: Skill 'missing' not found" in res_no_skill.content

    # 2. Insecure path traversal script name
    res_bad_path = await ctx.tools.execute(
        ToolCallData(
            call_id="c2",
            name="run_skill_script",
            arguments={"skill_name": "runner", "script_name": "../secret.sh"},
        )
    )
    assert "Error: Invalid or insecure script name" in res_bad_path.content

    # 3. Missing script file
    res_missing_file = await ctx.tools.execute(
        ToolCallData(
            call_id="c3",
            name="run_skill_script",
            arguments={"skill_name": "runner", "script_name": "not_there.sh"},
        )
    )
    assert "Error: Script not found" in res_missing_file.content

    # 4. No execution service mounted
    res_no_shell = await ctx.tools.execute(
        ToolCallData(
            call_id="c4",
            name="run_skill_script",
            arguments={"skill_name": "runner", "script_name": "test.sh"},
        )
    )
    assert (
        "Error: No shell or sandbox execution service mounted" in res_no_shell.content
    )

    # 5. Execution via ctx.shell
    mock_shell = AsyncMock()
    mock_shell.run.return_value = ShellResult(
        exit_code=0,
        stdout="script output ok",
        stderr="",
        timed_out=False,
        aborted=False,
        bytes_read=16,
    )
    ctx._register_service("shell", mock_shell)

    res_shell = await ctx.tools.execute(
        ToolCallData(
            call_id="c5",
            name="run_skill_script",
            arguments={
                "skill_name": "runner",
                "script_name": "test.sh",
                "args": ["--flag"],
            },
        )
    )
    assert "[Exit Code: 0]" in res_shell.content
    assert "script output ok" in res_shell.content

    # 6. Execution via ctx.sandbox
    mock_sandbox = AsyncMock()
    mock_sandbox.run.return_value = ShellResult(
        exit_code=0,
        stdout="sandboxed script ok",
        stderr="",
        timed_out=False,
        aborted=False,
        bytes_read=19,
    )
    ctx._register_service("sandbox", mock_sandbox)

    res_sandbox = await ctx.tools.execute(
        ToolCallData(
            call_id="c6",
            name="run_skill_script",
            arguments={"skill_name": "runner", "script_name": "test.sh"},
        )
    )
    assert "sandboxed script ok" in res_sandbox.content


async def test_skills_service_layer_discovery_and_disposal(tmp_path: Path) -> None:
    ctx = Context()
    ctx.use(ToolService)
    ctx.use(SystemPromptService)
    await ctx.flush()

    # Create dummy layer directory structure
    user_layer_dir = tmp_path / "user_agents"
    skills_in_layer = user_layer_dir / "skills"
    _create_dummy_skill(skills_in_layer, "layer-skill")

    # Mock ctx.layers
    mock_layers = MagicMock()
    mock_layers.get_layers.return_value = [
        ConfigLayer(name="user", path=user_layer_dir, exists=True),
        ConfigLayer(
            name="project", path=tmp_path / "non_existent_project", exists=False
        ),
    ]
    ctx._register_service("layers", mock_layers)

    fiber = ctx.use(SkillsBridgeService)
    await ctx.flush()
    service: SkillsBridgeService = ctx.skills

    discovered = service.discover_skills()
    assert "layer-skill" in discovered
    assert ctx.tools.get("activate_skill") is not None

    # Unload fiber
    await fiber.dispose()
    assert ctx.tools.get("activate_skill") is None
    assert len(service.skills) == 0


async def test_skills_service_edge_cases(tmp_path: Path) -> None:
    ctx = Context()
    service = SkillsBridgeService(ctx)

    # 1. Non-existent directory returns []
    assert service.discover_from_directory(tmp_path / "non-existent") == []

    # 2. Corrupted skill file handled with warning
    bad_dir = tmp_path / "corrupted"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("not a valid skill")
    assert service.discover_from_directory(bad_dir) == []

    # 3. discover_skills without layers on ctx
    assert service.discover_skills() == []

    # 4. update_prompt_catalog and mount_tools without system_prompt/tools
    service.update_prompt_catalog()
    service.mount_tools()

    # 5. update_prompt_catalog and mount_tools called multiple times
    ctx.use(ToolService)
    ctx.use(SystemPromptService)
    await ctx.flush()

    _create_dummy_skill(tmp_path / "valid", "multi-skill")
    service.discover_from_directory(tmp_path / "valid")
    service.update_prompt_catalog()
    service.update_prompt_catalog()  # hits self._prompt_disposer is not None branch
    service.mount_tools()
    service.mount_tools()  # hits for d in self._tool_disposers branch
    assert ctx.tools.get("activate_skill") is not None

    # 6. Dispose a fiber where prompt_disposer is None
    ctx_no_prompt = Context()
    fiber_no_prompt = ctx_no_prompt.use(SkillsBridgeService)
    await ctx_no_prompt.flush()
    await fiber_no_prompt.dispose()
