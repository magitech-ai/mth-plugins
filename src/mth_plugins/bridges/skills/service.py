"""SkillsBridgeService: Discovers SKILL.md packages and provides catalog."""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any

from anima import Context, Disposer, Service
from magitech_harness.tools.definition import Tool

from mth_plugins.bridges.skills.parser import SkillPackage, parse_skill_file

logger = logging.getLogger("mth_plugins.bridges.skills")


class SkillsBridgeService(Service):
    """Manages skill discovery, prompt catalog, and skill execution tools."""

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx, "skills")
        self.skills: dict[str, SkillPackage] = {}
        self._prompt_disposer: Disposer | None = None
        self._tool_disposers: list[Disposer] = []

        def _cleanup() -> None:
            if self._prompt_disposer is not None:
                self._prompt_disposer()
                self._prompt_disposer = None
            for d in self._tool_disposers:
                d()
            self._tool_disposers.clear()
            self.skills.clear()

        self.ctx.effect(lambda: _cleanup)

    def discover_from_directory(self, base_dir: Path) -> list[str]:
        """Scans a base directory for all SKILL.md files."""
        if not base_dir.is_dir():
            return []

        discovered: list[str] = []
        for skill_file in sorted(base_dir.glob("**/SKILL.md")):
            try:
                pkg = parse_skill_file(skill_file)
                self.skills[pkg.name] = pkg
                discovered.append(pkg.name)
            except Exception as e:
                logger.warning("Failed parsing skill file at %s: %s", skill_file, e)

        return discovered

    def discover_skills(self, explicit_dir: Path | str | None = None) -> list[str]:
        """Discovers skills across active layers or an explicit directory."""
        all_discovered: list[str] = []

        if explicit_dir is not None:
            all_discovered.extend(self.discover_from_directory(Path(explicit_dir)))
        elif self.ctx.has("layers"):
            layers = self.ctx.layers.get_layers()
            for layer in layers:
                if layer.exists:
                    skills_dir = layer.path / "skills"
                    all_discovered.extend(self.discover_from_directory(skills_dir))

        self.update_prompt_catalog()
        self.mount_tools()
        return all_discovered

    def update_prompt_catalog(self) -> None:
        """Injects a compact XML skills catalog into ctx.system_prompt."""
        if self._prompt_disposer is not None:
            self._prompt_disposer()
            self._prompt_disposer = None

        if not self.skills or not self.ctx.has("system_prompt"):
            return

        lines: list[str] = ["<skills>"]
        for pkg in self.skills.values():
            lines.append("  <skill>")
            lines.append(f"    <name>{pkg.name}</name>")
            lines.append(f"    <description>{pkg.description}</description>")
            lines.append(f"    <location>{pkg.skill_file.as_posix()}</location>")
            lines.append("  </skill>")
        lines.append("</skills>")

        catalog_xml = "\n".join(lines)
        self._prompt_disposer = self.ctx.system_prompt.register_section(
            "skills_catalog", catalog_xml
        )

    def mount_tools(self) -> None:
        """Registers activate_skill and run_skill_script onto ctx.tools."""
        if not self.ctx.has("tools"):
            return

        # Clear existing tool disposers before re-registering
        for d in self._tool_disposers:
            d()
        self._tool_disposers.clear()

        # Tool 1: activate_skill
        async def _handle_activate(args: dict[str, Any]) -> str:
            name = str(args.get("name", "")).strip()
            pkg = self.skills.get(name)
            if pkg is None:
                avail = list(self.skills.keys())
                return f"Error: Skill '{name}' not found. Available skills: {avail}"
            return f"# Skill: {pkg.name}\n\n{pkg.body}"

        activate_tool = Tool(
            name="activate_skill",
            description="Load and read the full instructions of an Agent Skill.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The unique name of the skill to activate.",
                    }
                },
                "required": ["name"],
            },
            handler=_handle_activate,
        )
        self._tool_disposers.append(self.ctx.tools.register(activate_tool))

        # Tool 2: run_skill_script
        async def _handle_run_script(args: dict[str, Any]) -> str:
            skill_name = str(args.get("skill_name", "")).strip()
            pkg = self.skills.get(skill_name)
            if pkg is None:
                return f"Error: Skill '{skill_name}' not found."

            script_name = str(args.get("script_name", "")).strip()
            if (
                not script_name
                or ".." in script_name
                or Path(script_name).is_absolute()
            ):
                return f"Error: Invalid or insecure script name: '{script_name}'."

            script_path = pkg.path / "scripts" / script_name
            if not script_path.is_file():
                return f"Error: Script not found: {script_path.as_posix()}"

            script_args = [str(a) for a in args.get("args", [])]
            cmd = shlex.join([str(script_path.resolve()), *script_args])

            if self.ctx.has("sandbox"):
                res = await self.ctx.sandbox.run(cmd, cwd=pkg.path)
            elif self.ctx.has("shell"):
                res = await self.ctx.shell.run(cmd, cwd=pkg.path)
            else:
                return (
                    "Error: No shell or sandbox execution service mounted on context."
                )

            status_str = f"[Exit Code: {res.exit_code}]\n"
            output = res.stdout.strip() or res.stderr.strip()
            return f"{status_str}{output}"

        script_tool = Tool(
            name="run_skill_script",
            description="Execute a script bundled inside an Agent Skill package.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Unique name of the skill with the script.",
                    },
                    "script_name": {
                        "type": "string",
                        "description": "Filename of script in skill's scripts/ dir.",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional CLI arguments to pass to the script.",
                    },
                },
                "required": ["skill_name", "script_name"],
            },
            handler=_handle_run_script,
        )
        self._tool_disposers.append(self.ctx.tools.register(script_tool))
