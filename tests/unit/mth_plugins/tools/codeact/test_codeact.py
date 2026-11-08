"""Unit tests for CodeActExecutor execution and tool auto-dispatching."""

from typing import Any

import pytest
from anima import Context
from magitech_harness.tools.definition import Tool
from magitech_harness.tools.service import ToolService

from mth_plugins.tools.codeact.codeact import CodeActExecutor


@pytest.fixture
def ctx() -> Context:
    context = Context()
    ToolService(context)
    return context


@pytest.mark.asyncio
async def test_codeact_execute_math_and_last_expr(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    result = await executor.execute("x = 15\ny = 25\nx + y")
    assert result == "40"
    assert executor.session_locals["x"] == 15
    assert executor.session_locals["y"] == 25


@pytest.mark.asyncio
async def test_codeact_execute_no_last_expr(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    result = await executor.execute("a = 100")
    assert result == "Execution completed successfully."
    assert executor.session_locals["a"] == 100


@pytest.mark.asyncio
async def test_codeact_execute_final_answer(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    code = """
total = sum([1, 2, 3, 4, 5])
final_answer(total)
"""
    result = await executor.execute(code)
    assert result == "Final Answer: 15"


@pytest.mark.asyncio
async def test_codeact_session_locals_persistence(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    # Turn 1: define function and variable
    await executor.execute(
        """
def greet(name: str) -> str:
    return f"Hello, {name}!"

val = 42
"""
    )

    # Turn 2: use defined function and variable from turn 1
    res = await executor.execute(
        """
res = greet("Magitech")
f"{res} Number: {val * 2}"
"""
    )
    assert res == "Hello, Magitech! Number: 84"


@pytest.mark.asyncio
async def test_codeact_syntax_and_validation_errors(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    # Syntax error
    res_syntax = await executor.execute("def unclosed(:")
    assert "CodeAct Error" in res_syntax

    # Forbidden import
    res_forbidden = await executor.execute("import os")
    assert "CodeAct Error: Forbidden module import: 'os'" in res_forbidden


@pytest.mark.asyncio
async def test_codeact_runtime_exception(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    res = await executor.execute("1 / 0")
    assert "Execution Error: division by zero" in res


@pytest.mark.asyncio
async def test_codeact_tool_dispatching(ctx: Context) -> None:
    tools_svc: ToolService = ctx.tools

    async def mock_read(args: dict[str, Any]) -> str:
        return f"Content of {args.get('path')}"

    tools_svc.register(
        Tool(
            name="read_file",
            description="Read file",
            parameters={"path": {"type": "string"}},
            handler=mock_read,
        )
    )

    executor = CodeActExecutor(ctx)
    assert "read_file" in executor.get_registered_tool_names()

    # Call with positional arg
    res1 = await executor.execute("read_file('test.txt')")
    assert res1 == "Content of test.txt"

    # Call with keyword arg
    res2 = await executor.execute("read_file(path='data.json')")
    assert res2 == "Content of data.json"


@pytest.mark.asyncio
async def test_codeact_tool_dispatch_errors(ctx: Context) -> None:
    tools_svc: ToolService = ctx.tools

    async def failing_tool(args: dict[str, Any]) -> None:
        raise RuntimeError("disk failure")

    tools_svc.register(
        Tool(
            name="broken",
            description="Broken tool",
            parameters={},
            handler=failing_tool,
        )
    )

    executor = CodeActExecutor(ctx)

    # Broken tool error
    res_fail = await executor.execute("broken()")
    assert "Execution Error: Tool 'broken' failed:" in res_fail
    assert "disk failure" in res_fail

    # Unregistered tool call in dispatch_tool directly
    with pytest.raises(NameError, match="Tool 'unknown' is not registered"):
        await executor.dispatch_tool("unknown")


@pytest.mark.asyncio
async def test_codeact_top_level_statements_and_locals(ctx: Context) -> None:
    executor = CodeActExecutor(ctx)
    code = """
count: int = 1
bare_val: int
count += 5
items = [1, 2]
items[0] += 10
items[0] = 99
class Holder:
    attr: int = 0
h = Holder()
h.attr: int = 50
msg = "hello"
msg_upper = msg.upper()
if False:
    unexecuted_var = 123
def add_one(val: int) -> int:
    return val + 1

async def async_add_two(val: int) -> int:
    return val + 2

class Calculator:
    pass

count
"""
    res = await executor.execute(code)
    assert res == "6"
    assert "count" in executor.session_locals
    assert "unexecuted_var" not in executor.session_locals
    assert "add_one" in executor.session_locals
    assert "async_add_two" in executor.session_locals
    assert "Calculator" in executor.session_locals


@pytest.mark.asyncio
async def test_codeact_tool_fallback_signature_and_content_error(ctx: Context) -> None:
    tools_svc: ToolService = ctx.tools

    async def sum_tool(args: dict[str, Any]) -> int:
        return args["a"] + args["b"]

    tools_svc.register(
        Tool(
            name="sum_numbers",
            description="Sum tool",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            handler=sum_tool,
        )
    )

    executor = CodeActExecutor(ctx)
    res = await executor.execute("sum_numbers(10, 20)")
    assert res == "30"

    # Extra positional argument
    res_extra = await executor.execute("sum_numbers(10, 20, 999)")
    assert res_extra == "30"

    # Tool returning result where content.is_error is True
    class CustomErrResult:
        is_error = True
        content = "custom inner error"

    async def err_tool(args: dict[str, Any]) -> CustomErrResult:
        return CustomErrResult()

    tools_svc.register(
        Tool(
            name="err_inner",
            description="Err tool",
            parameters={},
            handler=err_tool,
        )
    )

    res_inner = await executor.execute("err_inner()")
    assert "Execution Error: Tool 'err_inner' failed: custom inner error" in res_inner


def test_codeact_registry_fallback_variations() -> None:
    # 1. tools service without _registry but with list_all
    class MockToolsWithListAll:
        def list_all(self) -> list[Any]:
            return [Tool(name="t1", description="", parameters={})]

    ctx1 = Context()
    ctx1.tools = MockToolsWithListAll()
    ex1 = CodeActExecutor(ctx1)
    assert ex1.get_registered_tool_names() == {"t1"}

    # 2. tools service with non-callable list_all and no _registry
    class MockEmptyTools:
        pass

    ctx2 = Context()
    ctx2.tools = MockEmptyTools()
    ex2 = CodeActExecutor(ctx2)
    assert ex2.get_registered_tool_names() == set()


@pytest.mark.asyncio
async def test_codeact_missing_tool_service() -> None:
    empty_ctx = Context()
    executor = CodeActExecutor(empty_ctx)
    assert executor.get_registered_tool_names() == set()

    with pytest.raises(RuntimeError, match="ToolService not mounted"):
        await executor.dispatch_tool("any_tool")
