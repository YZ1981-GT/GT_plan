"""任务 2.2：附注公式类端点复用一次共享视图上下文 —— 真 ORM / 真 SQLite + 真 FastAPI 请求。

spec: consol-node-key-isolation-and-shared-context（需求 1.2、1.5、2.1；设计 §四，ADR-CNSC-003）。

本任务目标：``/refresh``、``/audit``、``/audit-all``、``/apply-formulas``、``/aggregate``、差额穿透与
``fill-by-formula`` 在一次请求内复用同一份节点作用域解析与合并视图上下文，而非各自重建树 / 重解析 / 重取数。

被测真实生产函数（禁 mock 替换被测函数本身）：
  - ``consol_note_scope.load_note_request_context``  一次请求只解析一次作用域 + 装载一次视图上下文
  - ``consol_note_scope.NoteRequestContext.node_measures``  ``node_measures(basis)`` 的请求级缓存（只算一次）
  - ``consol_note_formula_service.note_breakdown(..., request_ctx=)``  复用共享上下文求值
  - ``consol_note_formula_service.fill_by_formula(..., request_ctx=)``  内部 note_breakdown 复用同一上下文
  - 五个旧公式端点经 ``load_note_request_context`` 校验节点身份：非法键 ⇒ 明确 HTTP 错误；旧调用兼容

企业树身份用 ``group`` 夹具真实构建（G⊃A⊃A1, G⊃B；G:consol 为根，A:consol 为子合并节点）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.consolidation_models import EliminationEntryType
from app.services.consol_note_scope import (
    LegacyScope,
    NodeScope,
    NoteRequestContext,
    NoteScopeError,
    load_note_request_context,
)

# 复用推送测试的真集团与端点夹具。
from tests.test_consol_push import (  # noqa: F401
    Y,
    _entry,
    _persist,
    _User,
    client_for,
    db,
    factory,
    group,
)
from tests.test_consol_note_formulas import note_client  # noqa: F401

D = Decimal
_NS = "/api/consol-note-sections"


async def _generate_reports(db, project):
    """生成合并报表（breakdown/fill 的 REPORT() 取数依赖报表配置与已生成报表）。"""
    from app.services.consol_report_service import generate_consol_reports_sync

    await generate_consol_reports_sync(db, project.id, Y)
    await db.commit()


# ─────────────────── load_note_request_context：一次解析 + 一次装载 ───────────────────


class TestRequestContext:
    @pytest.mark.asyncio
    async def test_root_node_builds_scope_and_view_once(self, db, group):
        """根节点：产出 NodeScope（is_root_consol）+ 已装载视图上下文；project/year/node_key 对齐。"""
        ctx = await load_note_request_context(db, group["G"].id, Y, node_key="G:consol")
        assert isinstance(ctx, NoteRequestContext)
        assert isinstance(ctx.scope, NodeScope)
        assert ctx.scope.node_key == "G:consol" and ctx.scope.is_root_consol is True
        assert ctx.project_id == group["G"].id
        assert ctx.year == Y
        assert ctx.node_key == "G:consol"
        # 视图上下文确实装载（企业树根 = G:consol）
        assert ctx.view.basis.tree.node_key == "G:consol"

    @pytest.mark.asyncio
    async def test_legacy_call_builds_legacy_scope(self, db, group):
        """未传 node_key：LegacyScope + 仍装载视图上下文（合并项目），年度取项目审计年度。"""
        ctx = await load_note_request_context(db, group["G"].id, None, node_key=None)
        assert isinstance(ctx.scope, LegacyScope)
        assert ctx.node_key is None
        assert ctx.year == Y

    @pytest.mark.asyncio
    async def test_node_measures_cached_within_request(self, db, group):
        """``node_measures()`` 是请求级缓存：两次调用返回同一对象（只算一遍，复用是本任务的核心）。"""
        ctx = await load_note_request_context(db, group["G"].id, Y, node_key="G:consol")
        first = ctx.node_measures()
        second = ctx.node_measures()
        assert first is second, "node_measures 必须缓存，一次请求只遍历整棵树一遍"

    @pytest.mark.asyncio
    async def test_find_node_uses_shared_tree(self, db, group):
        """``find_node`` 复用上下文内已构建的企业树；company_code 取自验证过的树节点。"""
        ctx = await load_note_request_context(db, group["G"].id, Y, node_key="A:consol")
        node = ctx.find_node()
        assert node.node_key == "A:consol"
        assert node.company_code == "A", "company_code 从验证过的树节点取，非 node_key.split(':')"

    @pytest.mark.asyncio
    async def test_illegal_node_key_rejected_400(self, db, group):
        with pytest.raises(NoteScopeError) as exc:
            await load_note_request_context(db, group["G"].id, Y, node_key="ZZ:consol")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_non_consol_project_rejected_404(self, db, group):
        with pytest.raises(NoteScopeError) as exc:
            await load_note_request_context(db, group["B"].id, Y, node_key=None)
        assert exc.value.status == 404


# ─────────────────── note_breakdown / fill_by_formula 复用共享上下文 ───────────────────


class TestBreakdownReuse:
    @pytest.mark.asyncio
    async def test_breakdown_with_request_ctx_matches_standalone(self, db, group):
        """传 request_ctx 与不传得到同样的 cells（复用上下文不改变正确性，P5）。"""
        from app.services.consol_note_formula_service import note_breakdown

        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        await db.commit()
        await _generate_reports(db, group["G"])

        without = await note_breakdown(db, group["G"].id, Y, "五-1-1", node_key="G:consol")
        await db.commit()
        ctx = await load_note_request_context(db, group["G"].id, Y, node_key="G:consol")
        withctx = await note_breakdown(db, group["G"].id, Y, "五-1-1", node_key="G:consol", request_ctx=ctx)
        await db.commit()

        cells_a = {(c["row_index"], c["col_index"]): c["consolidated"] for c in without["cells"]}
        cells_b = {(c["row_index"], c["col_index"]): c["consolidated"] for c in withctx["cells"]}
        assert cells_a == cells_b, "复用共享上下文求值必须与独立装载一致"
        assert withctx["node_key"] == "G:consol"

    @pytest.mark.asyncio
    async def test_fill_threads_single_context(self, db, group, monkeypatch):
        """fill_by_formula 传 request_ctx 时，整条「填入」请求只建一次树（内部 note_breakdown 复用）。

        用引用计数证据：patch load_view_context 计数真实装载次数；传 ctx 后 fill 内部不再触发装载。
        """
        from app.services import consol_report_view_service as view_svc

        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        await db.commit()
        await _generate_reports(db, group["G"])

        calls = {"n": 0}
        real_load = view_svc.load_view_context

        async def _counting(db_, pid, yr=None):
            calls["n"] += 1
            return await real_load(db_, pid, yr)

        # note_breakdown 内 _context 从 view 模块 import load_view_context ⇒ patch 模块属性即可计数
        monkeypatch.setattr(view_svc, "load_view_context", _counting)

        ctx = await load_note_request_context(db, group["G"].id, Y, node_key="G:consol")
        before = calls["n"]  # load_note_request_context 自己装载一次（计入）
        from app.services.consol_note_formula_service import fill_by_formula

        await fill_by_formula(db, group["G"].id, Y, "五-1-1", node_key="G:consol", request_ctx=ctx)
        await db.commit()
        assert calls["n"] == before, "传入共享上下文后，fill 内部不得再次装载视图上下文"


# ─────────────────── 端点级：节点身份校验 + 旧调用兼容（真 FastAPI 请求） ───────────────────


class TestEndpointSharedContext:
    @pytest.mark.asyncio
    async def test_illegal_node_key_rejected_by_formula_endpoints(self, db, group, note_client):
        """五个旧公式端点 + 穿透 + 填入：显式非法 node_key ⇒ 明确 400（经共享上下文校验，不再裸推导）。"""
        from app.models.base import UserRole
        from tests.test_consol_push import _User

        gid = str(group["G"].id)
        await _generate_reports(db, group["G"])
        admin = _User(UserRole.admin)
        bad = {"node_key": "ZZ:consol"}
        async with note_client(admin) as c:
            cases = [
                c.post(f"{_NS}/refresh/{gid}/{Y}/五-1-1", params=bad, json={"standard": "soe"}),
                c.post(f"{_NS}/audit/{gid}/{Y}/五-1-1", params=bad, json={"standard": "soe"}),
                c.post(f"{_NS}/audit-all/{gid}/{Y}", params=bad, json={"standard": "soe"}),
                c.post(f"{_NS}/apply-formulas/{gid}/{Y}", params=bad, json={"standard": "soe"}),
                c.post(f"{_NS}/aggregate/{gid}/{Y}", params=bad, json={"section_id": "五-1-1"}),
                c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1", params=bad),
                c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/五-1-1", params=bad),
            ]
            for coro in cases:
                resp = await coro
                assert resp.status_code == 400, f"非法 node_key 应被明确拒绝：{resp.request.url} -> {resp.text}"

    @pytest.mark.asyncio
    async def test_legacy_calls_without_node_key_still_work(self, db, group, note_client):
        """旧调用（不传 node_key）仍走项目级兼容路径，不被共享上下文升级为节点请求（ADR-CNSC-002）。"""
        from app.models.base import UserRole
        from tests.test_consol_push import _User

        gid = str(group["G"].id)
        await _generate_reports(db, group["G"])
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            for coro in (
                c.post(f"{_NS}/refresh/{gid}/{Y}/五-1-1", json={"standard": "soe"}),
                c.post(f"{_NS}/audit/{gid}/{Y}/五-1-1", json={"standard": "soe"}),
                c.post(f"{_NS}/audit-all/{gid}/{Y}", json={"standard": "soe"}),
                c.post(f"{_NS}/apply-formulas/{gid}/{Y}", json={"standard": "soe"}),
            ):
                resp = await coro
                assert resp.status_code == 200, f"旧调用应兼容放行：{resp.request.url} -> {resp.text}"

    @pytest.mark.asyncio
    async def test_valid_node_key_accepted(self, db, group, note_client):
        """合法节点键（根 / 子合并节点）被接受；端点经验证的树节点取 company_code。"""
        from app.models.base import UserRole
        from tests.test_consol_push import _User

        gid = str(group["G"].id)
        await _generate_reports(db, group["G"])
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            for nk in ("G:consol", "A:consol", "B:subsidiary"):
                resp = await c.post(f"{_NS}/audit/{gid}/{Y}/五-1-1", params={"node_key": nk},
                                    json={"standard": "soe"})
                assert resp.status_code == 200, f"合法节点键 {nk} 应被接受：{resp.text}"
