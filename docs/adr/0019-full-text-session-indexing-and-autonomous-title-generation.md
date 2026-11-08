# 0019. Full-Text Session Indexing and Autonomous Title Generation

Date: 2026-11-08
Status: accepted

## Context

Agents accumulate extensive conversational histories stored across individual JSONL session files. Users and agents need to:
1. Perform high-performance lexical search across past session contents, roles, and tool executions.
2. Maintain concise, human-meaningful session titles without requiring manual user labeling or blocking interactive agent turns.

## Decision

We implement `session-search` and `session-title` plugins in `mth-plugins`:
1. **SQLite FTS5 Full-Text Search (`session-search`)**:
   - Persists a dedicated search database (`~/.agents/session_search.db`).
   - Maintains tables for `conversations` (metadata, total steps, file mtime) and `messages` (turn step, role, type, content, tool names).
   - Utilizes an SQLite `fts5` virtual table with the `porter unicode61` tokenizer and automated database triggers syncing message rows to the index.
   - Provides an incremental file indexer scanning session directories by modified timestamp (`mtime`).
   - Exposes the `session_search` tool enabling agents and interfaces to query historical sessions with relevance ranking.
2. **Autonomous Titling Service (`session-title`)**:
   - On the first completed turn of a session, extracts an instant fallback title (<8 words, <=96 bytes) from the initial user prompt.
   - Triggers an asynchronous, non-blocking background LLM completion to generate a polished, descriptive title (<10 words, <=120 bytes).
   - Implements restored title protection: resumed sessions or sessions with pinned titles are protected from being overwritten.

## Consequences

- Search queries execute with sub-millisecond latency using SQLite FTS5 index structures.
- Sessions receive immediate, meaningful labels without user effort or perceived agent turn latency.
- Historical context is searchable without reading hundreds of raw JSONL files on every query.
