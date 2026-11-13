"""附注三端点鉴权守卫（AST）—— 写端点挂附注编辑门禁、读端点挂只读项目访问.

Spec:    .kiro/specs/formula-manager-closure/ Task 4.1（原 ADR-FMC-07）
更新：    附注写端点的鉴权已由 ``require_project_access("edit")`` 升级为更合适的**附注编辑门禁**
         ``require_note_edit_access(consol_lock=True)``（见 ``app.services.note_edit_gate`` / memory
         「附注写操作走附注编辑门禁」）—— 它在 edit 级之上还做归档校验、EQCR 只读、操作矩阵（全局角色∪
         项目角色）与合并锁，是严格的超集。守卫随实现更新为按**真实鉴权形态**校验，不再锁死 edit 字面量。

当前基线：
- apply_formulas       → require_note_edit_access(consol_lock=True)   （写：附注编辑门禁 + 合并锁）
- upsert_note_formulas → require_note_edit_access(consol_lock=True)   （写：同上）
- list_note_formulas   → require_project_access("readonly")           （读：只读项目访问）

铁律㉖：一律用 **AST** 判断函数签名默认值里的 ``Depends(...)`` 调用，不用文本 ``in`` 匹配
（文本会被 docstring / 注释正反两向骗过）。
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.routers import disclosure_notes


def _signature_defaults(func) -> list[ast.AST]:
    """函数签名里全部参数默认值节点（位置 + 关键字）。只看签名 —— docstring 是
    ``Expr(Constant)``、``#`` 注释不进 AST，天然排除，不会被文档/注释里的同名串骗过。"""
    src = _dedent(inspect.getsource(func))
    mod = ast.parse(src)
    fn = mod.body[0]
    assert isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
    return list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]


def _call_name(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _calls_named(func, name: str) -> list[ast.Call]:
    """签名默认值子树里所有名为 *name* 的调用节点（递归）。"""
    out: list[ast.Call] = []
    for node in _signature_defaults(func):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and _call_name(sub) == name:
                out.append(sub)
    return out


def _project_access_levels(func) -> list[str]:
    """签名里 ``require_project_access("<level>")`` 的 level 字面量。"""
    return [c.args[0].value for c in _calls_named(func, "require_project_access")
            if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str)]


def _note_edit_consol_locks(func) -> list[bool]:
    """签名里 ``require_note_edit_access(consol_lock=<bool>)`` 的 consol_lock 字面量。"""
    out: list[bool] = []
    for c in _calls_named(func, "require_note_edit_access"):
        for kw in c.keywords:
            if kw.arg == "consol_lock" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
                out.append(kw.value.value)
    return out


def _dedent(src: str) -> str:
    lines = src.splitlines()
    if not lines:
        return src
    indent = len(lines[0]) - len(lines[0].lstrip())
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines)


@pytest.mark.parametrize("func_name", ["apply_formulas", "upsert_note_formulas"])
def test_note_write_endpoint_uses_note_edit_gate(func_name):
    """附注写端点（执行公式 / 保存公式）必须挂 ``require_note_edit_access(consol_lock=True)``。

    这是比 ``require_project_access('edit')`` 更严格的附注编辑门禁（归档 / EQCR / 操作矩阵 / 合并锁），
    且写端点涉及合并锁适用集合，须 ``consol_lock=True``。不得被整体摘掉、不得降级为只读。
    """
    func = getattr(disclosure_notes, func_name)
    locks = _note_edit_consol_locks(func)
    assert locks == [True], (
        f"{func_name} 必须恰挂一个 require_note_edit_access(consol_lock=True)，实际 AST 抽出 {locks!r} —— "
        f"附注写端点须保持附注编辑门禁（写操作不得降级或摘除鉴权）。"
    )
    # 写端点不应再用只读项目访问（防止被误降级）
    assert _project_access_levels(func) == [], (
        f"{func_name} 不应再挂 require_project_access（写端点已改用 require_note_edit_access）。"
    )


def test_note_list_endpoint_is_readonly_project_access():
    """附注公式列表端点（读）必须恰挂一个 ``require_project_access('readonly')``。"""
    levels = _project_access_levels(disclosure_notes.list_note_formulas)
    assert levels == ["readonly"], (
        f"list_note_formulas 的 require_project_access 级别应为 ['readonly']，实际 AST 抽出 {levels!r}。"
    )


def test_all_three_note_endpoints_have_access_control():
    """三端点都必须有鉴权依赖（写 = 附注编辑门禁，读 = 只读项目访问），防被整体摘掉。"""
    for func_name in ("apply_formulas", "upsert_note_formulas"):
        func = getattr(disclosure_notes, func_name)
        assert _note_edit_consol_locks(func), f"{func_name} 缺 require_note_edit_access 依赖（附注写端点须保持）"
    assert _project_access_levels(disclosure_notes.list_note_formulas), (
        "list_note_formulas 缺 require_project_access 依赖"
    )
