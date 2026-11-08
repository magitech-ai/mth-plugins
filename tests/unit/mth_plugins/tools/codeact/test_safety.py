"""Unit tests for AST safety and write-protection visitors."""

import ast

import pytest

from mth_plugins.tools.codeact.codeact import ASTSafetyVisitor, WriteProtectionVisitor


def test_ast_safety_allowed_imports() -> None:
    code = """
import math
import json
import re
from collections import defaultdict, Counter
from typing import Any, Optional
val = math.pi
obj_attr = str.upper("hello")
"""
    parsed = ast.parse(code)
    ASTSafetyVisitor().visit(parsed)


def test_ast_safety_forbidden_imports() -> None:
    bad_snippets = [
        "import os",
        "import sys",
        "import subprocess",
        "from os import path",
        "import socket",
        "import urllib.request",
        "from urllib import parse",
        "from . import something",
    ]
    for snip in bad_snippets:
        parsed = ast.parse(snip)
        with pytest.raises(
            ValueError, match=r"Forbidden module import|Relative imports are forbidden"
        ):
            ASTSafetyVisitor().visit(parsed)


def test_write_protection_allowed_constructs() -> None:
    protected = {"read_file", "final_answer", "__dispatch__"}
    safe_code = """
x = 10
(a, b) = (1, 2)
[c, d] = [3, 4]
y: int = 20
y += 5
(z := 30)
def my_func(): pass
async def my_async_func(): pass
class MyClass: pass
data = [1, 2]
data[0] = 99
"""
    parsed = ast.parse(safe_code)
    WriteProtectionVisitor(protected).visit(parsed)


def test_ast_safety_forbidden_attributes() -> None:
    bad_snippets = [
        "os.system('id')",
        "sys.exit(1)",
        "subprocess.run(['ls'])",
    ]
    for snip in bad_snippets:
        parsed = ast.parse(snip)
        with pytest.raises(ValueError, match="Forbidden attribute access"):
            ASTSafetyVisitor().visit(parsed)


def test_ast_safety_forbidden_calls() -> None:
    bad_snippets = [
        "eval('2 + 2')",
        "exec('x = 1')",
        "open('secret.txt')",
        "__import__('os')",
    ]
    for snip in bad_snippets:
        parsed = ast.parse(snip)
        with pytest.raises(ValueError, match="Forbidden function call"):
            ASTSafetyVisitor().visit(parsed)


def test_write_protection_forbidden_reassignments() -> None:
    protected = {"read_file", "final_answer", "__dispatch__"}
    bad_snippets = [
        "final_answer = 123",
        "a, read_file = 1, 2",
        "[read_file] = [10]",
        "(x, (y, final_answer)) = (1, (2, 3))",
        "final_answer: int = 10",
        "final_answer += 1",
        "(final_answer := 5)",
        "def read_file(): pass",
        "async def read_file(): pass",
        "class final_answer: pass",
    ]
    for snip in bad_snippets:
        parsed = ast.parse(snip)
        with pytest.raises(
            ValueError, match="Cannot overwrite protected tool or keyword"
        ):
            WriteProtectionVisitor(protected).visit(parsed)
