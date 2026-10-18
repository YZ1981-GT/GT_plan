"""Task 4.1 / ADR-FMC-07 — 附注三端点鉴权未被改动（AST 守卫）.

Spec:    .kiro/specs/formula-manager-closure/ Task 4.1
Design:  ADR-FMC-04 / ADR-FMC-07、§1 #12

附注三端点 apply_formulas / list_note_formulas / upsert_note_formulas 的
``require_project_access`` 级别在本任务**保持不变**（ADR-FMC-07）：
- apply_formulas   → require_project_access("edit")
- list_note_formulas → require_project_access("readonly")
- upsert_note_formulas → require_project_access("edit")

铁律㉖：一律用 **AST** 判断函数签名里 ``Depends(require_project_access("..."))``，
不用文本 ``in`` 匹配（文本会被 docstring / 注释正反两向骗过）。
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.routers import disclosure_notes


def _access_levels_from_signature(func) -> list[str]:
    """用 AST 从函数签名的参数默认值里抽出所有
    ``Depends(require_project_access("<level>"))`` 的 level 字面量。

    只看签名默认值（``args.defaults`` / ``args.kw_defaults``）——
    docstring 是 ``Expr(Constant)``、``#`` 注释根本不进 AST，故天然排除，
    不会被注释/文档里出现的同名字符串骗过。
    """
    src = inspect.getsource(func)
    src = _dedent(src)
    mod = ast.parse(src)
    fn = mod.body[0]
    assert isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))

    levels: list[str] = []
    defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
    for node in defaults:
        for call in _iter_require_project_access_calls(node):
            if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                levels.append(call.args[0].value)
    return levels


def _iter_require_project_access_calls(node: ast.AST):
    """递归找出子树里所有 ``require_project_access(...)`` 调用节点。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name == "require_project_access":
                yield sub


def _dedent(src: str) -> str:
    lines = src.splitlines()
    if not lines:
        return src
    indent = len(lines[0]) - len(lines[0].lstrip())
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines)


@pytest.mark.parametrize(
    "func_name, expected_level",
    [
        ("apply_formulas", "edit"),
        ("list_note_formulas", "readonly"),
        ("upsert_note_formulas", "edit"),
    ],
)
def test_note_endpoint_auth_level_unchanged(func_name, expected_level):
    """三端点各自恰挂一个 require_project_access，且级别与基线一致（AST）。"""
    func = getattr(disclosure_notes, func_name)
    levels = _access_levels_from_signature(func)
    assert levels == [expected_level], (
        f"{func_name} 的 require_project_access 级别应为 [{expected_level!r}]，"
        f"实际 AST 抽出 {levels!r} —— 本任务（ADR-FMC-07）不得改动附注端点鉴权。"
    )


def test_all_three_note_endpoints_have_project_access():
    """三端点都必须有 require_project_access 依赖（防被整体摘掉）。"""
    for func_name in ("apply_formulas", "list_note_formulas", "upsert_note_formulas"):
        func = getattr(disclosure_notes, func_name)
        levels = _access_levels_from_signature(func)
        assert levels, f"{func_name} 缺 require_project_access 依赖（ADR-FMC-07 要求保持）"
