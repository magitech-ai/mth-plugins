# ADR 0014: In-Process CodeAct Execution and Tool Auto-Dispatching

## Status
Accepted

## Date
2026-11-08

## Context
Language models often solve complex multi-step reasoning problems most effectively by writing executable Python code. However, executing model-synthesized code directly on the host poses severe security risks, while spawning an external REPL daemon over IPC introduces high latency and serialization friction for nested tool calls.

Furthermore, model code must be able to call other registered tools directly as Python functions (e.g. `read(path="...")`, `bash(command="...")`) while ensuring that the execution of those nested tools still respects policy approvals and privilege boundaries.

## Decision
1. **In-Process AST Transformation & Safe Builtins**:
   The `codeact-tool` compiles Python snippets in-process using Python's `ast` engine:
   - Evaluates code with a restricted `__builtins__` namespace excluding arbitrary evaluation (`eval`, `exec`, `open`, `__import__`).
   - Imports are validated against an allowlist of pure standard-library modules (`math`, `json`, `re`, `datetime`, `collections`, `itertools`, `copy`, `heapq`, `bisect`, `typing`).
2. **AST Write Protection**:
   An AST visitor scans assignment targets, type annotations, and function/class definitions to forbid shadowing or reassigning registered tool names or control keywords (`final_answer`, `__dispatch__`).
3. **Auto-`await` Tool Dispatching**:
   The transformer converts calls to registered tool names into `await __dispatch__(tool_name, *args, **kwargs)` inside an asynchronous wrapper coroutine. When invoked, `__dispatch__` routes the execution through the harness tool service, ensuring that approval gates, rate limits, and audit logs are triggered identically to direct LLM tool calls.
4. **Session Locals Persistence**:
   A session-scoped dictionary persists module-level variables across turns in the same conversation, allowing multi-turn iterative code experimentation.
5. **Clean Turn Termination via `final_answer(value)`**:
   Expose `final_answer(value)` which raises a dedicated termination signal caught by the executor to return the final answer.

## Consequences
- **Positive**: Zero IPC overhead when orchestrating complex sequences of tools.
- **Positive**: Transparent policy enforcement—nested tool calls cannot bypass approval checks.
- **Positive**: Complete AST safety prevents arbitrary filesystem or network escape from within Python itself; any I/O is routed through sandboxed tools.
