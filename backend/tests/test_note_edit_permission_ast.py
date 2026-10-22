"""AST 可伪证断言：附注编辑权限判定查询端点（需求 10.1）。

partner-manager-edit-permission Task 13.2

断言的都是「如果这些约束被打破，测试立刻打红」的结构性保证：
  ① 端点函数体调用 ``assert_note_edit_access`` 与 ``is_project_eqcr``。
  ② 除签名中的 readonly 鉴权外，不调用 ``assert_project_permission``、
     不查委派表（``ProjectAssignment``）、不与 ``"eqcr"`` 字面量比较。
  ③ 签名含 ``require_project_access("readonly")``。
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROUTER_FILE = Path(__file__).resolve().parents[1] / "app" / "routers" / "note_edit_permission.py"


def _parse_endpoint() -> ast.AsyncFunctionDef:
    """解析 ``get_note_edit_permission`` 的 AST 节点。"""
    src = _ROUTER_FILE.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_note_edit_permission":
            return node
    raise AssertionError("找不到 get_note_edit_permission 函数")


def _all_name_refs(node: ast.AST) -> set[str]:
    """收集 AST 子树内全部 Name.id 与 Attribute.attr 引用（跳过 docstring / 字符串常量）。"""
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            names.add(n.attr)
    return names


def _all_string_literals(node: ast.AST) -> list[str]:
    """收集函数体内全部字符串字面量（含 docstring，但 docstring 不产生 Name）。"""
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


# ─── 断言 ───────────────────────────────────────────────────────────────────


def test_endpoint_calls_assert_note_edit_access():
    """① 函数体调用 ``assert_note_edit_access``（需求 10.1）。"""
    node = _parse_endpoint()
    names = _all_name_refs(node)
    assert "assert_note_edit_access" in names, (
        "get_note_edit_permission 不再调用 assert_note_edit_access"
    )


def test_endpoint_calls_is_project_eqcr():
    """① 函数体调用 ``is_project_eqcr``（需求 10.1：is_eqcr 一律给出）。"""
    node = _parse_endpoint()
    names = _all_name_refs(node)
    assert "is_project_eqcr" in names, (
        "get_note_edit_permission 不再调用 is_project_eqcr"
    )


def test_endpoint_does_not_call_assert_project_permission():
    """② 除签名 readonly 鉴权外，不调 ``assert_project_permission``。

    签名里的 ``require_project_access("readonly")`` 内部会调 assert_project_permission，
    但端点函数体自身不应再显式调用它——判定全委托给 assert_note_edit_access。
    """
    node = _parse_endpoint()
    # 只检查函数体语句（不含签名 defaults）
    body_names: set[str] = set()
    for stmt in node.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Name):
                body_names.add(n.id)
            elif isinstance(n, ast.Attribute):
                body_names.add(n.attr)
    assert "assert_project_permission" not in body_names, (
        "get_note_edit_permission 函数体内不应直接调用 assert_project_permission"
    )


def test_endpoint_does_not_query_assignments_table():
    """② 不查委派表：函数体不引用 ProjectAssignment。"""
    node = _parse_endpoint()
    names = _all_name_refs(node)
    assert "ProjectAssignment" not in names, (
        "get_note_edit_permission 不应直接查委派表——EQCR 判定委托给 is_project_eqcr"
    )


def test_endpoint_does_not_compare_eqcr_literal():
    """② 不与 ``"eqcr"`` 字面量比较。"""
    node = _parse_endpoint()
    # 排除 docstring（第一个语句如果是 Expr(Constant(str))）
    body_stmts = node.body
    if (body_stmts and isinstance(body_stmts[0], ast.Expr)
            and isinstance(body_stmts[0].value, ast.Constant)
            and isinstance(body_stmts[0].value.value, str)):
        body_stmts = body_stmts[1:]
    eqcr_lits = []
    for stmt in body_stmts:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Constant) and n.value == "eqcr":
                eqcr_lits.append(n)
    assert not eqcr_lits, (
        f"get_note_edit_permission 含 'eqcr' 字面量（{len(eqcr_lits)} 处），应委托 is_project_eqcr 判定"
    )


def test_endpoint_signature_has_readonly_auth():
    """③ 签名含 ``require_project_access("readonly")``。"""
    node = _parse_endpoint()
    # 检查 defaults / kw_defaults 里的 Depends(require_project_access("readonly"))
    all_defaults = list(node.args.defaults) + list(node.args.kw_defaults)
    found = False
    for d in all_defaults:
        if d is None:
            continue
        # Depends(require_project_access("readonly"))
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "Depends":
            for arg in d.args:
                if isinstance(arg, ast.Call):
                    func = arg.func
                    func_name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                    if func_name == "require_project_access":
                        for a in arg.args:
                            if isinstance(a, ast.Constant) and a.value == "readonly":
                                found = True
    assert found, (
        "get_note_edit_permission 签名缺少 require_project_access('readonly') 依赖"
    )
