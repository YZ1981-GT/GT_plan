"""附注端点必须逐个具备项目级门禁（防 IDOR）。

Feature: advanced-query-hardening-wiring-closure（收口顺带修复）

背景：``test_disclosure_notes_hardening.py`` 的 33 条红长期被登记为「路由已重构」而搁置。
逐端点核对后发现那是**误判** —— 那批测试指向的洞至今仍在，只是它们断言的是旧机制
（模块级 ``assert_note_edit_access`` / ``assert_note_edit_access_for_object`` / ``OwnershipGuard`` / 函数体内调用顺序），机制变了就
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

需求 6.10（spec partner-manager-edit-permission 任务 6.5）：文末另有附注编辑门禁判定实现的可伪证断言，其判定函数
``note_gate_ast_facts`` 由鉴权基线守卫复用。
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
    "assert_note_edit_access",  # 附注编辑门禁判定实现（归档 → review → EQCR → 矩阵 → 合并锁）
    "assert_note_edit_access_for_object",  # 附注编辑门禁对象反查形态
    "assert_project_permission",
    "assert_target_accessible",  # OwnershipGuard（读路径）
    "_assert_note_project_access",
    "_assert_object_project_access",
    # 交付中心同一判定（首句 assert_project_permission，再按交付件角色矩阵 + EQCR 只读）：导出 Word 用。
    # 「它真的校验项目成员」由 test_project_endpoint_authorization_baseline 的可伪证断言钉住
    "_guard_action",
}

#: 业务动作调用名 —— 门禁必须早于它们全部。
#: 不含 ``execute``：``db.execute``（最小投影反查）与
#: ``DisclosureMutationCoordinator.execute`` 同名，会互相误判；coordinator 用
#: ``_coordinator`` 工厂名识别。
BUSINESS_CALLS = {
    "generate_notes",
    "update_note",
    "trace_cell",
    "check",  # PrerequisiteChecker.check
    "_coordinator",  # mutation 协调器（内部 commit）
    "confirm_finding",
}

#: 依赖注入型门禁
DEPENDS_GATES = {"require_project_access", "require_role", "require_wp_edit_permission", "require_note_edit_access"}

#: 无项目数据、无需项目门禁的端点（逐个写明理由，不是兜底通道）
NO_PROJECT_DATA = {
    # 致同附注 Word 排版规范常量（21 项），全平台同一份，不含任何项目数据
    "get_format_config",
    # 恒抛 501（历史 Word/PDF 解析未实现）：不声明 DB 依赖、不执行任何业务动作，
    # 无数据可读可写。加门禁反而会为一个未实现能力占用连接池。
    "upload_history",
    # 附注模块能力清单（哪些入口可用 + 中文原因），全平台同一份，不含项目数据
    "get_capabilities",
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
        ("generate_notes", "assert_note_edit_access"),
        ("update_note", "assert_note_edit_access_for_object"),
        ("confirm_finding", "assert_note_edit_access_for_object"),
        ("trace_cell", "assert_target_accessible"),
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
    """门禁必须早于一切业务动作。

    不能简单要求「门禁是第一条 await」—— 路径上只有 note_id / validation_id 的端点必须
    **先最小反查所属项目**才知道该鉴权哪个项目，那条 SELECT 合法地排在门禁之前。
    故判据是：
      1. 门禁出现在所有业务调用（engine / checker / coordinator）之前；
      2. 门禁之前最多只允许一条 ``db.execute``（即那条最小投影反查），不得有第二次读。
    """

    FUNCS = ("generate_notes", "update_note", "confirm_finding", "trace_cell")

    @staticmethod
    def _call_lines(node: ast.AST) -> list[tuple[int, str]]:
        out = []
        for c in ast.walk(node):
            if isinstance(c, ast.Call):
                name = getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                if name:
                    out.append((c.lineno, name))
        return sorted(out)

    @pytest.mark.parametrize("func_name", FUNCS)
    def test_gate_precedes_all_business_calls(self, func_name):
        calls = self._call_lines(_func_nodes()[func_name])
        gate_lines = [ln for ln, n in calls if n in BODY_GATES]
        assert gate_lines, f"{func_name} 没有任何项目门禁调用"
        gate_at = min(gate_lines)
        business = [(ln, n) for ln, n in calls if n in BUSINESS_CALLS and ln > 0]
        # 端点函数自身的名字也会出现在 BUSINESS_CALLS 里（如 update_note 调 engine.update_note），
        # 只看晚于门禁的即可；早于门禁的才是违规。
        violations = [(ln, n) for ln, n in business if ln < gate_at]
        assert not violations, (
            f"{func_name} 在门禁（第 {gate_at} 行）之前就调了业务动作：{violations}"
            " —— 403 之前不得读到/改到别人项目的数据"
        )

    @pytest.mark.parametrize("func_name", FUNCS)
    def test_at_most_one_read_before_gate(self, func_name):
        calls = self._call_lines(_func_nodes()[func_name])
        gate_at = min(ln for ln, n in calls if n in BODY_GATES)
        reads_before = [ln for ln, n in calls if n == "execute" and ln < gate_at]
        assert len(reads_before) <= 1, (
            f"{func_name} 在门禁前有 {len(reads_before)} 次 db.execute —— "
            "只允许一条『最小投影反查 project_id』，多出来的就是未鉴权的业务读"
        )


def test_helper_resolves_project_before_permission_check():
    """反查型门禁自身的顺序：先 SELECT project_id，再做权限判定。

    若顺序颠倒（先鉴权后反查），鉴权对象就不是被操作对象所属项目。

    同时验证新增的附注编辑门禁对象反查形态 ``assert_note_edit_access_for_object``
    也遵守「反查先于鉴权」。
    """
    # ─── 旧反查型门禁（trace_cell 仍在用）───
    src = inspect.getsource(notes_router._assert_object_project_access)
    tree = ast.parse(src.lstrip())
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

    # ─── 附注编辑门禁对象反查形态 ───
    from app.services.note_edit_gate import assert_note_edit_access_for_object
    src2 = inspect.getsource(assert_note_edit_access_for_object)
    tree2 = ast.parse(src2.lstrip())
    seq2 = sorted(
        (
            (node.lineno, name)
            for node in ast.walk(tree2)
            if isinstance(node, ast.Call)
            and (name := getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in ("select", "assert_note_edit_access")
        )
    )
    names2 = [n for _, n in seq2]
    assert "select" in names2 and "assert_note_edit_access" in names2, names2
    assert names2.index("select") < names2.index("assert_note_edit_access"), (
        f"附注编辑门禁对象反查形态的反查与鉴权顺序颠倒：{seq2}"
    )


class TestOwnershipGuardPatchabilityNotShadowed:
    """归属守卫单例上不得残留实例属性 —— 它会让类级替身静默失效。

    实测踩过：``test_advanced_query_hardening_properties_scope`` 用「读出原绑定方法 →
    ``finally`` 再赋回**实例**」的写法做替身恢复。哪怕赋回的值就是原绑定方法，实例
    ``__dict__`` 里也**永久**多了一个 ``assert_target_accessible``，它遮蔽类属性 ⇒ 之后任何
    ``patch("...OwnershipGuard.assert_target_accessible")`` 都打不上 ⇒ 本文件与
    ``test_disclosure_notes_hardening`` 的 trace 越权用例在**合跑**时莫名变红，而单跑全绿。

    这类「跨文件污染」最难查，故用一条结构判据钉住：单例不得自带该属性。
    """

    def test_singleton_has_no_instance_level_override(self):
        from app.services.custom_query.ownership_guard import (
            OwnershipGuard,
            ownership_guard,
        )

        leaked = set(vars(ownership_guard)) & {"assert_target_accessible"}
        assert not leaked, (
            "ownership_guard 单例上残留了实例属性 "
            f"{sorted(leaked)} —— 它会遮蔽类属性，使类级 patch 失效。"
            "测试替身请 patch 类（或用 monkeypatch），恢复时删实例属性而不是赋回绑定方法。"
        )
        # 反向自检：类上确实有这个方法，否则上一条恒绿
        assert callable(getattr(OwnershipGuard, "assert_target_accessible", None))

    def test_class_level_patch_is_observable(self, monkeypatch):
        """行为判据：类级替身必须真的被实例调用观测到。"""
        from app.services.custom_query.ownership_guard import (
            OwnershipGuard,
            ownership_guard,
        )

        seen: list[str] = []

        async def _fake(self, *, user, project_id, db):  # noqa: ANN001
            seen.append(str(project_id))

        monkeypatch.setattr(OwnershipGuard, "assert_target_accessible", _fake)
        import asyncio

        asyncio.run(
            ownership_guard.assert_target_accessible(user=None, project_id="p-1", db=None)
        )
        assert seen == ["p-1"], "类级替身未被单例观测到（说明实例上有 shadow 属性）"


# ══════════════════════════════════════════════════════════════════════════
# 需求 6.10：附注编辑门禁判定实现的可伪证断言（spec partner-manager-edit-permission 任务 6.5）
# ══════════════════════════════════════════════════════════════════════════
#
# 附注编辑门禁（``app/services/note_edit_gate.py``）记作项目级门禁的前提是判定实现 ``assert_note_edit_access``
# ① 在条件分支与异常处理之外以 review 级调用 ``assert_project_permission``，② 调用 EQCR 判定 ``is_project_eqcr``。
# 两条都按 AST 判定：注释、docstring 与其他字符串里出现的名字不计。鉴权基线守卫
# （``test_project_endpoint_authorization_baseline.py``）导入 ``note_gate_ast_facts`` 放同口径的一组，并用其中的
# ``"role"`` 判角色限定形态 —— 改名或改键须同步那边。``BODY_GATES`` / ``CASES`` 等改看附注编辑门禁在任务 10.1。

#: 被判定的门禁源码。测试在调用时读取：变异实测可把它指向源码副本，不必改磁盘上的生产文件。
NOTE_GATE_PATH = ROUTER_PATH.parents[1] / "services" / "note_edit_gate.py"


def _module_bindings(tree: ast.Module, name: str) -> list[ast.AST]:
    """全模块里绑定 ``name`` 的节点：import、def / class、赋值或删除的目标、形参、``except … as``。"""
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found += [node for alias in node.names if (alias.asname or alias.name.split(".")[0]) == name]
        elif (
            (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler))
             and node.name == name)
            or (isinstance(node, ast.Name) and node.id == name and not isinstance(node.ctx, ast.Load))
            or (isinstance(node, ast.arg) and node.arg == name)
        ):
            found.append(node)
    return found


def _unique_async_def(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | None:
    """``name`` 全模块只有一处绑定且是模块级 ``async def`` 时返回它；另有同名赋值、定义、导入或形参都返回 None。"""
    bound = _module_bindings(tree, name)
    if len(bound) == 1 and isinstance(bound[0], ast.AsyncFunctionDef) and bound[0] in tree.body:
        return bound[0]
    return None


def _unconditional_awaits(func: ast.AsyncFunctionDef | None) -> list[tuple[str, ast.Call]]:
    """函数体顶层、第一条含 ``return`` 的语句之前，``await f(...)`` / ``x = await f(...)`` 里被 await 的按名调用。

    不进入 if / try / for / while / with：其中的调用不是无条件执行；排在可能提前 return 的语句之后的也不算。
    """
    if func is None:
        return []
    calls: list[tuple[str, ast.Call]] = []
    for stmt in func.body:
        if any(isinstance(node, ast.Return) for node in ast.walk(stmt)):
            break
        value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)) else None
        call = value.value if isinstance(value, ast.Await) else None
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            calls.append((call.func.id, call))
    return calls


def _is_review_level(tree: ast.Module, arg: ast.expr) -> bool:
    """级别实参是字面量 ``"review"``，或值为 ``"review"`` 的同文件常量（模块级单目标赋值，全模块只有这一处绑定）。"""
    if isinstance(arg, ast.Name):
        assigned = [
            stmt.value
            for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == arg.id
        ]
        if len(assigned) != 1 or len(_module_bindings(tree, arg.id)) != 1:
            return False
        arg = assigned[0]
    return isinstance(arg, ast.Constant) and arg.value == "review"


def note_gate_ast_facts(src: str) -> dict[str, bool]:
    """附注编辑门禁源码的三条结构事实（按 AST），键与含义：

    - ``"permission"``（需求 6.10 ①）：判定实现无条件 await ``assert_project_permission``，级别实参（第 4 个位置实参或
      ``min_permission=``，恰好一个）为 review；该名字只绑定于 ``from app.deps import assert_project_permission``。
    - ``"eqcr"``（需求 6.10 ②）：判定实现无条件 await ``is_project_eqcr``；该名字只绑定于
      ``from app.services.eqcr_resolver import is_project_eqcr``（唯一的 EQCR 判定，需求 7.3）。
    - ``"role"``：角色限定形态 ``assert_note_role_access`` 无条件 await 判定实现（鉴权基线守卫用）。

    判定实现与角色限定形态都须是全模块唯一绑定的模块级 ``async def``；「无条件」的口径见 ``_unconditional_awaits``。
    """
    tree = ast.parse(src)
    gate = _unique_async_def(tree, "assert_note_edit_access")
    gate_calls = _unconditional_awaits(gate)
    role_calls = _unconditional_awaits(_unique_async_def(tree, "assert_note_role_access"))

    def bound_only_by_import(name: str, module: str) -> bool:
        return [getattr(node, "module", None) for node in _module_bindings(tree, name)] == [module]

    levels = [
        call.args[3:4] + [kw.value for kw in call.keywords if kw.arg == "min_permission"]
        for name, call in gate_calls
        if name == "assert_project_permission"
    ]
    return {
        "permission": bound_only_by_import("assert_project_permission", "app.deps")
        and any(len(level) == 1 and _is_review_level(tree, level[0]) for level in levels),
        "eqcr": bound_only_by_import("is_project_eqcr", "app.services.eqcr_resolver")
        and any(name == "is_project_eqcr" for name, _call in gate_calls),
        "role": gate is not None and any(name == "assert_note_edit_access" for name, _call in role_calls),
    }


class TestNoteEditGateIsFalsifiable:
    """需求 6.10 的两条断言，作用于磁盘上真实的门禁源码（鉴权基线守卫另放同口径的一组）。"""

    def test_requires_review_membership_unconditionally(self):
        """① 判定实现在条件分支、异常处理与提前 return 之外 await ``assert_project_permission``，级别 review。"""
        facts = note_gate_ast_facts(NOTE_GATE_PATH.read_text(encoding="utf-8"))
        assert facts["permission"], (
            f"{NOTE_GATE_PATH.name}：assert_note_edit_access 不再无条件以 review 级（字面量或同文件常量）调用 "
            "app.deps.assert_project_permission —— 级别被改、调用移入分支 / try、未 await 或该名字被覆盖"
        )

    def test_calls_eqcr_judgment(self):
        """② 判定实现无条件 await 唯一的 EQCR 判定 ``app.services.eqcr_resolver.is_project_eqcr``。"""
        facts = note_gate_ast_facts(NOTE_GATE_PATH.read_text(encoding="utf-8"))
        assert facts["eqcr"], (
            f"{NOTE_GATE_PATH.name}：assert_note_edit_access 不再无条件调用 EQCR 判定 is_project_eqcr "
            "—— 调用被删、移入分支或不是 app.services.eqcr_resolver 那一个"
        )


_SAMPLE_HEAD = (
    "from app.deps import assert_project_permission\n"
    "from app.services.eqcr_resolver import is_project_eqcr\n"
    'LEVEL = "review"\n'
    "async def assert_note_edit_access(db, user, project_id, *, consol_lock):\n"
)
_PERMISSION_OK = "    await assert_project_permission(db, user, project_id, LEVEL)\n"
_EQCR_OK = "    is_eqcr = await is_project_eqcr(db, user, project_id)\n"
_ROLE_HEAD = "async def assert_note_role_access(db, user, project_id, *, project_roles, denied_message):\n"
_ROLE_JUDGMENT = "    await assert_note_edit_access(db, user, project_id, consol_lock=False)\n"

#: 合成样例（拼在 ``_SAMPLE_HEAD`` 之后）→ (permission, eqcr, role) 的期望值：每条事实成立 / 不成立两个方向都有
_FACT_SAMPLES: dict[str, tuple[str, tuple[bool, bool, bool]]] = {
    "constant-level": (_PERMISSION_OK + _EQCR_OK, (True, True, False)),
    "keyword-literal-level": (
        '    await assert_project_permission(db, user, project_id, min_permission="review")\n' + _EQCR_OK,
        (True, True, False),
    ),
    "edit-level": (
        '    await assert_project_permission(db, user, project_id, "edit")\n' + _EQCR_OK,
        (False, True, False),
    ),
    "default-level": ("    await assert_project_permission(db, user, project_id)\n" + _EQCR_OK, (False, True, False)),
    "permission-inside-if": ("    if user.role != 'admin':\n    " + _PERMISSION_OK + _EQCR_OK, (False, True, False)),
    "permission-inside-try": (
        "    try:\n    " + _PERMISSION_OK + "    except Exception:\n        pass\n" + _EQCR_OK,
        (False, True, False),
    ),
    "after-early-return": (
        "    if user is None:\n        return None\n" + _PERMISSION_OK + _EQCR_OK,
        (False, False, False),
    ),
    "permission-not-awaited": (
        "    assert_project_permission(db, user, project_id, LEVEL)\n" + _EQCR_OK,
        (False, True, False),
    ),
    "mentioned-only-in-docstring-and-comment": (
        '    """await assert_project_permission(db, user, project_id, LEVEL)；await is_project_eqcr(...)"""\n'
        "    # await assert_project_permission(db, user, project_id, LEVEL)\n"
        "    return user\n",
        (False, False, False),
    ),
    "permission-shadowed": (
        _PERMISSION_OK + _EQCR_OK + "def assert_project_permission(*args):\n    return None\n",
        (False, True, False),
    ),
    "level-rebound": (_PERMISSION_OK + _EQCR_OK + 'LEVEL = "edit"\n', (False, True, False)),
    "eqcr-deleted": (_PERMISSION_OK, (True, False, False)),
    "eqcr-inside-if": (_PERMISSION_OK + "    if user.role != 'admin':\n    " + _EQCR_OK, (True, False, False)),
    "eqcr-redefined": (
        _PERMISSION_OK + _EQCR_OK + "async def is_project_eqcr(*args):\n    return False\n",
        (True, False, False),
    ),
    "role-runs-judgment": (
        _PERMISSION_OK + _EQCR_OK + _ROLE_HEAD + _ROLE_JUDGMENT + "    return user\n",
        (True, True, True),
    ),
    "role-skips-judgment": (_PERMISSION_OK + _EQCR_OK + _ROLE_HEAD + "    return user\n", (True, True, False)),
    "role-returns-before-judgment": (
        _PERMISSION_OK + _EQCR_OK + _ROLE_HEAD + "    if user.role == 'admin':\n        return user\n" + _ROLE_JUDGMENT,
        (True, True, False),
    ),
}


@pytest.mark.parametrize("sample", sorted(_FACT_SAMPLES))
def test_note_gate_ast_facts_on_samples(sample):
    """自检：判定函数对合成样例逐条给对 —— 防退化为恒真 / 恒假；注释与 docstring 里的名字不算调用。"""
    body, expected = _FACT_SAMPLES[sample]
    facts = note_gate_ast_facts(_SAMPLE_HEAD + body)
    assert (facts["permission"], facts["eqcr"], facts["role"]) == expected, facts
