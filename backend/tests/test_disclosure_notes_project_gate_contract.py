"""附注端点必须逐个具备项目级门禁（防 IDOR）。

Feature: advanced-query-hardening-wiring-closure（收口顺带修复）

背景：``test_disclosure_notes_hardening.py`` 的 33 条红长期被登记为「路由已重构」而搁置。
逐端点核对后发现那是**误判** —— 那批测试指向的洞至今仍在，只是它们断言的是旧机制
（模块级 ``_assert_project_edit`` / ``OwnershipGuard`` / 函数体内调用顺序），机制变了就
全部 AttributeError，于是「测试挂了」被当成「测试过时了」。

实测 34 个端点里有 7 个存在真实归属缺口：

===================================  ====  ==========================================
端点                                 读写  缺口
===================================  ====  ==========================================
POST /generate                       写    project_id 在 **body**，require_project_access
                                           取不到 ⇒ 任何登录用户可为任意项目生成附注
PUT  /{note_id}                      写    只挂 require_operation，其 project_id 从路径取，
                                           本端点没有 ⇒ 退化为**仅按 system_role 判**
                                           ⇒ 可改任意项目的附注章节
PUT  /findings/{vid}/confirm          写    挂了 require_project_access 但路径无 project_id
                                           ⇒ FastAPI 变成**查询参数** ⇒ 传一个自己有权的
                                           项目即可确认**别的项目**的校验发现
POST /{pid}/{year}/pull-from-...      写    完全无门禁
GET  /{note_id}/cells/.../trace       读    完全无门禁（可读别的项目的溯源链与试算表证据）
GET  /{pid}/{year}/linkage-gaps       读    完全无门禁
GET  /{pid}/{year}/{sec}/auto-pull    读    完全无门禁
===================================  ====  ==========================================

本文件用**路由表契约**代替原来的「函数体内调用顺序」断言：遍历 router 的每个端点，要求
它要么挂了取得到 project_id 的依赖门禁，要么在函数体里显式调用按对象反查的门禁。这比原
判据更强 —— 它对**将来新增的端点**同样生效，而旧判据只覆盖当时写死的那几个函数名。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.routers import disclosure_notes as notes_router

ROUTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "routers"
    / "disclosure_notes.py"
)

#: 函数体内显式调用的门禁（用于 project_id 不在路径上的端点）
BODY_GATES = {
    "assert_project_permission",
    "_assert_note_project_access",
    "_assert_validation_project_access",
    "_assert_object_project_access",
}

#: 依赖注入型门禁
DEPENDS_GATES = {"require_project_access", "require_role", "require_wp_edit_permission"}

#: 无项目数据、无需项目门禁的端点（逐个写明理由，不是兜底通道）
NO_PROJECT_DATA = {
    # 致同附注 Word 排版规范常量（21 项），全平台同一份，不含任何项目数据
    "get_format_config",
}


def _endpoints() -> list[tuple[str, str, str]]:
    """返回 [(method, path, func_name)]，取自真实 router 路由表。"""
    out: list[tuple[str, str, str]] = []
    for route in notes_router.router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        for method in sorted(getattr(route, "methods", []) or []):
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append((method, getattr(route, "path", "?"), endpoint.__name__))
    return out


def _func_nodes() -> dict[str, ast.AST]:
    tree = ast.parse(ROUTER_PATH.read_text(encoding="utf-8"))
    return {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _gate_of(func_name: str, node: ast.AST) -> str | None:
    """返回该端点使用的门禁名；无门禁返回 None。"""
    # 1) 依赖注入型：只看签名（默认值里的 Depends(...)）
    for default in getattr(node.args, "defaults", []) or []:
        for call in ast.walk(default):
            if isinstance(call, ast.Call):
                name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                if name in DEPENDS_GATES:
                    return name
    # 2) 函数体内显式调用型
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            if name in BODY_GATES:
                return name
    return None


class TestEveryEndpointHasProjectGate:
    def test_route_table_is_discoverable(self):
        """反向自检：必须真的枚举到一批端点，否则下面的判据会假绿。"""
        eps = _endpoints()
        assert len(eps) > 25, f"只枚举到 {len(eps)} 个端点，判据不可靠"

    def test_all_endpoints_gated(self):
        nodes = _func_nodes()
        ungated: list[str] = []
        for method, path, fname in _endpoints():
            if fname in NO_PROJECT_DATA:
                continue
            node = nodes.get(fname)
            if node is None:
                ungated.append(f"{method} {path} -> {fname}（源码里找不到该函数）")
                continue
            if _gate_of(fname, node) is None:
                ungated.append(f"{method} {path} -> {fname}")
        assert not ungated, (
            "以下附注端点没有任何项目级门禁（可跨项目访问 / 修改）：\n"
            + "\n".join("  " + u for u in ungated)
        )

    def test_gate_detector_can_fail(self):
        """反向自检：门禁探测器对一个确实无门禁的函数必须返回 None。"""
        src = "async def bogus(x: int, db=Depends(get_db)):\n    return x\n"
        node = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        assert _gate_of("bogus", node) is None


class TestBodyProjectIdEndpointsUseExplicitGate:
    """project_id 不在路径上的端点，不能靠 require_project_access。

    ``require_project_access`` 的内部依赖签名是 ``project_id: UUID`` —— 路径上没有它时
    FastAPI 会把它当成**必填查询参数**，于是门禁校验的是调用方自己挑的项目，而不是被
    操作对象所属的项目。这类端点必须用函数体内的反查型门禁。
    """

    CASES = (
        ("generate_notes", "assert_project_permission"),
        ("update_note", "_assert_note_project_access"),
        ("confirm_finding", "_assert_validation_project_access"),
        ("trace_cell", "_assert_note_project_access"),
    )

    @pytest.mark.parametrize("func_name,expected_gate", CASES)
    def test_uses_body_gate(self, func_name, expected_gate):
        node = _func_nodes()[func_name]
        calls = {
            getattr(c.func, "id", None) or getattr(c.func, "attr", None)
            for c in ast.walk(node)
            if isinstance(c, ast.Call)
        }
        assert expected_gate in calls, (
            f"{func_name} 未调用 {expected_gate}；它的 project_id 不在路径上，"
            "靠 require_project_access 会退化为「校验调用方自选的项目」"
        )

    @pytest.mark.parametrize("func_name,_gate", CASES)
    def test_does_not_rely_on_path_dependency(self, func_name, _gate):
        """这类端点的签名里不得出现 require_project_access（会变成查询参数陷阱）。"""
        node = _func_nodes()[func_name]
        for default in getattr(node.args, "defaults", []) or []:
            for call in ast.walk(default):
                if isinstance(call, ast.Call):
                    name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                    assert name != "require_project_access", (
                        f"{func_name} 路径无 project_id 却挂了 require_project_access —— "
                        "它会被 FastAPI 变成必填查询参数，门禁校验错对象"
                    )


class TestGateRunsBeforeBusinessRead:
    """反查型门禁必须是函数体的**第一条** await（先鉴权、再读业务数据）。"""

    FUNCS = ("generate_notes", "update_note", "confirm_finding", "trace_cell")

    @pytest.mark.parametrize("func_name", FUNCS)
    def test_gate_is_first_await(self, func_name):
        node = _func_nodes()[func_name]
        awaits = [n for n in ast.walk(node) if isinstance(n, ast.Await)]
        assert awaits, f"{func_name} 没有任何 await，判据失效"
        first = awaits[0]
        called = {
            getattr(c.func, "id", None) or getattr(c.func, "attr", None)
            for c in ast.walk(first)
            if isinstance(c, ast.Call)
        }
        assert called & BODY_GATES, (
            f"{func_name} 的第一条 await 不是项目门禁（实际调用：{sorted(x for x in called if x)}）"
            " —— 鉴权必须先于任何业务读写，否则 403 之前就已经读到/改到别人项目的数据"
        )


def test_helper_resolves_project_before_permission_check():
    """反查型门禁自身的顺序：先 SELECT project_id，再做权限判定。

    若顺序颠倒（先鉴权后反查），鉴权对象就不是被操作对象所属项目。
    """
    src = inspect.getsource(notes_router._assert_object_project_access)
    tree = ast.parse(src.lstrip())
    # 按**源码行号**排序 —— ast.walk 是广度优先，不反映书写顺序
    seq = sorted(
        (
            (node.lineno, name)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (name := getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in ("select", "assert_project_permission")
        )
    )
    names = [n for _, n in seq]
    assert "select" in names and "assert_project_permission" in names, names
    assert names.index("select") < names.index("assert_project_permission"), (
        f"反查与鉴权顺序颠倒：{seq}"
    )
