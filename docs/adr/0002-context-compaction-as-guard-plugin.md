# 0002. Context Compaction as a Guard Plugin

Date: 2026-11-07
Status: accepted

## Context

Conversations in multi-turn agent sessions grow over time, eventually exceeding model context windows. We must summarize history to fit within context limits without baking domain prompt opinions, token pressure heuristics, or slash command handling into the core runtime engine.

## Decision

We implement context compaction as an extensible guard plugin (`compaction-guard`):
1. The compaction plugin registers an interceptor on the Anima waterfall event `turn/stream`.
2. When prompt token pressure exceeds a configured threshold (or upon receiving an explicit `/compact` slash command), the plugin determines a balanced cut point using `is_tool_pairing_balanced`.
3. The plugin prompts the active LLM provider (`ctx.llm.generate`) with a structured summarization instruction covering goals, findings, and ongoing tasks.
4. The resulting summary is appended to the session log as an immutable `session/compaction` event, allowing the core projection engine to fold previous events for subsequent model calls.

## Consequences

- The core harness engine provides only the neutral projection seam, keeping the runtime clean and unopinionated.
- Token pressure thresholds, summarization prompts, and trigger conditions can be customized or replaced per profile.
- Compaction operations remain fully recorded and transparent within the session event history.
