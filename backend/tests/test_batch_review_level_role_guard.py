"""守卫：批量复核必须做层级角色校验（防 manager 越权执行 partner 层）。

缺陷来源（platform-release-blocker-closure Task 22 角色矩阵走查，2026-11-16 实测）：
``routers/batch_review.py`` 只依赖 ``require_project_access("review")``，
而 manager 的项目级别是 ``edit``（edit ≥ review ⇒ 放行），于是 manager 能直接执行
``level2_passed``（L2 = partner 层）。修复前实测回执 ``skipped=0 success=1`` 且底稿推进到
``level2_passed``；修复后 ``skipped=1 reason="当前为 L2 复核，仅允许项目合伙人角色处理"``。

本守卫用 AST 静态断言：``batch_review`` 端点函数体内必须调用
``assert_review_level_actor``（与单笔端点 ``wp_review_router`` 同一判据）。
纯静态，不连库。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "batch_review.py"

#: 必须出现在 batch_review 端点函数体里的层级角色校验函数名
REQUIRED_GUARD = "assert_review_level_actor"


def _module_ast() -> ast.Module:
    assert ROUTER.is_file(), f"找不到 {ROUTER}"
    return ast.parse(ROUTER.read_text(encoding="utf-8"))


def _find_endpoint(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{ROUTER.name} 里找不到端点函数 {name}")


def _called_names(func: ast.AST) -> set[str]:
    """函数体内被调用（Call）的简单名与属性名。"""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def _imported_names(func: ast.AST) -> set[str]:
    """函数体内 import 的名字（含 from ... import X）。"""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[-1])
    return names


@pytest.fixture(scope="module")
def endpoint() -> ast.AST:
    return _find_endpoint(_module_ast(), "batch_review")


def test_batch_review_calls_level_role_guard(endpoint: ast.AST) -> None:
    """batch_review 必须调用层级角色校验（AST，不看注释/docstring）。"""
    assert REQUIRED_GUARD in _called_names(endpoint), (
        f"batch_review 端点未调用 {REQUIRED_GUARD}："
        "manager 会越权执行 L2（partner 层）。"
        "修复见 platform-release-blocker-closure Task 22 角色矩阵走查。"
    )


def test_batch_review_imports_the_guard(endpoint: ast.AST) -> None:
    """该名字必须真的被导入（防止调用一个未定义名字而运行时 NameError）。"""
    assert REQUIRED_GUARD in _imported_names(endpoint), (
        f"batch_review 里没有 import {REQUIRED_GUARD}（可能只在别处定义）"
    )


def test_guard_is_shared_with_single_entry() -> None:
    """单笔端点与批量端点必须用同一个校验函数（单一来源，不各写一份）。"""
    single = (
        Path(__file__).resolve().parents[1] / "app" / "routers" / "wp_review_router.py"
    )
    assert single.is_file()
    tree = ast.parse(single.read_text(encoding="utf-8"))
    all_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                all_calls.add(target.id)
            elif isinstance(target, ast.Attribute):
                all_calls.add(target.attr)
    assert REQUIRED_GUARD in all_calls, (
        f"单笔端点 {single.name} 未调用 {REQUIRED_GUARD}；"
        "两个入口必须共用同一层级角色判据"
    )


def test_permission_error_is_handled_as_skip(endpoint: ast.AST) -> None:
    """PermissionError 必须被捕获为「跳过 + 原因」，不能冒泡成 500。"""
    handlers = [
        h for node in ast.walk(endpoint) if isinstance(node, ast.Try)
        for h in node.handlers
    ]
    caught: list[str] = []
    for h in handlers:
        t = h.type
        if isinstance(t, ast.Name):
            caught.append(t.id)
        elif isinstance(t, ast.Tuple):
            caught.extend(e.id for e in t.elts if isinstance(e, ast.Name))
    assert "PermissionError" in caught, (
        "batch_review 未捕获 PermissionError：角色不符会冒泡成 500 而不是逐项 skip"
    )
