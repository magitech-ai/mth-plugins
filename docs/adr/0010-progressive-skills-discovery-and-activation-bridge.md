# ADR 0010: Progressive Skills Discovery and Activation Bridge

## Status
Accepted

## Date
2026-11-08

## Context
Agent Skills following the `agentskills.io` standard bundle rich procedural documentation, workflows, and executable scripts into isolated directories containing a `SKILL.md` specification.

Loading the entire markdown body of every installed skill directly into the model's system prompt causes severe prompt bloat, token depletion, and attention degradation. A progressive disclosure architecture is required.

## Decision
1. **Lightweight Zero-Dependency Spec Parser**:
   Parse `SKILL.md` YAML frontmatter and markdown body using a built-in zero-dependency parser conforming to the `agentskills.io` specification (verifying `name`, `description`, and compatibility).

2. **Progressive Disclosure Prompt Catalog**:
   Rather than dumping full skill instructions into the system prompt, register a concise XML catalog section (`<skills><skill><name>...</name><description>...</description></skill></skills>`) on `ctx.system_prompt.register_section("skills_catalog", ...)`.

3. **Dynamic Skill Activation Tools**:
   Mount two specialized tools onto `ctx.tools`:
   - `activate_skill(name: str)`: Dynamically retrieves and injects the full markdown instructions of a requested skill only when needed.
   - `run_skill_script(skill_name: str, script_name: str, args: list[str])`: Executes bundled helper scripts in `{skill}/scripts/` with path traversal protections (`..` rejection) via `ctx.sandbox` or `ctx.shell`.

## Consequences
- **Positive**: Enables hundreds of skills to be available in a single agent session with near-zero baseline token overhead.
- **Positive**: Strict script path validation prevents path traversal outside the skill's sandbox directory.
