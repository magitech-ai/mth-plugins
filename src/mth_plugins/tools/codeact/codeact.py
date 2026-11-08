"""In-process CodeAct Python execution engine with tool auto-dispatching."""

from __future__ import annotations

import ast
import builtins
import uuid
from typing import Any

from anima import Context
from magitech_harness.tools.service import ToolCallData

SAFE_STDLIB_MODULES = frozenset(
    {
        "math",
        "json",
        "re",
        "datetime",
        "random",
        "collections",
        "itertools",
        "functools",
        "string",
        "copy",
        "heapq",
        "bisect",
        "typing",
    }
)

FORBIDDEN_NAMES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "eval",
        "exec",
        "open",
        "__import__",
        "builtins",
    }
)

SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bin",
        "bool",
        "bytes",
        "bytearray",
        "callable",
        "chr",
        "complex",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "locals",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "type",
        "vars",
        "zip",
        "__build_class__",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "StopIteration",
    )
}


class FinalAnswerError(Exception):
    """Raised by final_answer(value) to cleanly terminate execution."""

    def __init__(self, value: Any) -> None:
        super().__init__(str(value))
        self.value = value


FinalAnswerException = FinalAnswerError


def _resolve_attribute_root(node: ast.expr) -> str | None:
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


class ASTSafetyVisitor(ast.NodeVisitor):
    """Validates AST safety against forbidden modules, functions, and attributes."""

    def __init__(self, allowed_modules: frozenset[str] = SAFE_STDLIB_MODULES) -> None:
        self.allowed_modules = allowed_modules

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in FORBIDDEN_NAMES or base_mod not in self.allowed_modules:
                raise ValueError(f"Forbidden module import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module:
            raise ValueError("Relative imports are forbidden")
        base_mod = node.module.split(".")[0]
        if base_mod in FORBIDDEN_NAMES or base_mod not in self.allowed_modules:
            raise ValueError(f"Forbidden module import: '{node.module}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root = _resolve_attribute_root(node)
        if root and root in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden attribute access: '{root}.{node.attr}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden function call: '{node.func.id}'")
        self.generic_visit(node)


class WriteProtectionVisitor(ast.NodeVisitor):
    """Prevents code from shadowing or overwriting protected tools or keywords."""

    def __init__(self, protected_names: set[str]) -> None:
        self.protected_names = protected_names

    def _check_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name) and target.id in self.protected_names:
            raise ValueError(
                f"Cannot overwrite protected tool or keyword '{target.id}'"
            )
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._check_target(elt)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_target(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_target(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_target(node.target)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._check_target(node.target)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in self.protected_names:
            raise ValueError(
                f"Cannot overwrite protected tool or keyword '{node.name}'"
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name in self.protected_names:
            raise ValueError(
                f"Cannot overwrite protected tool or keyword '{node.name}'"
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name in self.protected_names:
            raise ValueError(
                f"Cannot overwrite protected tool or keyword '{node.name}'"
            )
        self.generic_visit(node)


class CodeActTransformer(ast.NodeTransformer):
    """Transforms registered tool invocations into async dispatch calls."""

    def __init__(self, tool_names: set[str]) -> None:
        self.tool_names = tool_names

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name == "final_answer":
                return ast.Call(
                    func=ast.Name(id="__final_answer__", ctx=ast.Load()),
                    args=node.args,
                    keywords=node.keywords,
                )
            if func_name in self.tool_names:
                dispatch_call = ast.Call(
                    func=ast.Name(id="__dispatch__", ctx=ast.Load()),
                    args=[ast.Constant(value=func_name), *node.args],
                    keywords=node.keywords,
                )
                return ast.Await(value=dispatch_call)
        return node


class CodeActExecutor:
    """In-process Python execution environment with tool dispatch."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.session_locals: dict[str, Any] = {}

    def get_registered_tool_names(self) -> set[str]:
        tools_svc = getattr(self.ctx, "tools", None)
        if tools_svc is None:
            return set()
        registry = getattr(tools_svc, "_registry", None)
        if isinstance(registry, dict):
            names = set(registry.keys())
        else:
            all_tools = getattr(tools_svc, "list_all", None)
            names = {t.name for t in all_tools()} if callable(all_tools) else set()
        names.discard("execute_python")
        return names

    async def dispatch_tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatches a nested tool call through ctx.tools."""
        tools_svc = getattr(self.ctx, "tools", None)
        if tools_svc is None:
            raise RuntimeError(f"ToolService not mounted; cannot invoke '{tool_name}'")

        tool = tools_svc.get(tool_name)
        if tool is None:
            raise NameError(f"Tool '{tool_name}' is not registered.")

        # Map positional arguments to keyword arguments using tool.parameters
        merged_kwargs = dict(kwargs)
        if args:
            param_names = list(tool.parameters.keys())
            for i, arg in enumerate(args):
                if i < len(param_names):
                    merged_kwargs[param_names[i]] = arg

        call_id = f"codeact_{uuid.uuid4().hex[:8]}"
        call_data = ToolCallData(
            call_id=call_id, name=tool_name, arguments=merged_kwargs
        )
        result = await tools_svc.execute(call_data)
        if getattr(result, "is_error", False):
            raise RuntimeError(f"Tool '{tool_name}' failed: {result.content}")
        content = getattr(result, "content", result)
        if hasattr(content, "is_error") and content.is_error:
            raise RuntimeError(f"Tool '{tool_name}' failed: {content.content}")
        return content

    def transform_code(
        self, code_str: str, tool_names: set[str]
    ) -> tuple[ast.Module, set[str]]:
        parsed = ast.parse(code_str)

        # 1. AST Safety check
        ASTSafetyVisitor().visit(parsed)

        # 2. Write-protection check
        protected = set(tool_names) | {
            "final_answer",
            "__dispatch__",
            "__final_answer__",
            "__last_expr__",
        }
        WriteProtectionVisitor(protected).visit(parsed)

        # 3. CodeAct transform tool calls to await __dispatch__
        transformer = CodeActTransformer(tool_names)
        transformed = transformer.visit(parsed)
        ast.fix_missing_locations(transformed)

        body = list(transformed.body)
        top_names: set[str] = set()
        for i, stmt in enumerate(body):
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        top_names.add(t.id)
            elif isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name):
                    top_names.add(stmt.target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    top_names.add(stmt.target.id)
                    if stmt.value is not None:
                        body[i] = ast.Assign(targets=[stmt.target], value=stmt.value)
                    else:
                        body[i] = ast.Pass()
            elif isinstance(
                stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                top_names.add(stmt.name)

        # Capture last expression
        if body and isinstance(body[-1], ast.Expr):
            last_expr = body[-1].value
            body[-1] = ast.Assign(
                targets=[ast.Name(id="__last_expr__", ctx=ast.Store())],
                value=last_expr,
            )

        init_last = ast.Assign(
            targets=[ast.Name(id="__last_expr__", ctx=ast.Store())],
            value=ast.Constant(value=None),
        )

        global_stmt = ast.Global(names=sorted(top_names | {"__last_expr__"}))
        func_body = [
            global_stmt,
            init_last,
            *body,
            ast.Return(value=ast.Name(id="__last_expr__", ctx=ast.Load())),
        ]

        func_def = ast.AsyncFunctionDef(
            name="__codeact_runner__",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="__dispatch__"),
                    ast.arg(arg="__final_answer__"),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=func_body,
            decorator_list=[],
            returns=None,
            type_params=[],
        )

        mod = ast.Module(body=[func_def], type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod, top_names

    async def execute(self, code: str) -> str:
        """Compiles and executes Python snippet with session state preservation."""
        tool_names = self.get_registered_tool_names()

        try:
            mod, top_names = self.transform_code(code, tool_names)
            compiled = compile(mod, filename="<codeact>", mode="exec")
        except (ValueError, SyntaxError) as exc:
            return f"CodeAct Error: {exc}"

        async def _dispatch_wrapper(
            tool_name: str, *t_args: Any, **t_kwargs: Any
        ) -> Any:
            return await self.dispatch_tool(tool_name, *t_args, **t_kwargs)

        def _final_answer_wrapper(val: Any) -> None:
            raise FinalAnswerException(val)

        exec_globals: dict[str, Any] = dict(self.session_locals)
        exec_globals["__name__"] = "__main__"
        exec_globals["__builtins__"] = dict(SAFE_BUILTINS)

        try:
            exec(compiled, exec_globals)
            runner = exec_globals["__codeact_runner__"]
            last_val = await runner(_dispatch_wrapper, _final_answer_wrapper)
        except FinalAnswerException as fa:
            return f"Final Answer: {fa.value}"
        except Exception as exc:
            return f"Execution Error: {exc}"

        # Persist session locals excluding runner/internal bindings
        for k in top_names:
            if k in exec_globals and not k.startswith("__"):
                self.session_locals[k] = exec_globals[k]

        if last_val is not None:
            return str(last_val)
        return "Execution completed successfully."
