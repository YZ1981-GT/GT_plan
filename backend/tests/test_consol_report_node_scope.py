"""任务 4.1：普通合并报表端点按节点读时计算 —— 入参扩展 + 节点/年度校验。

spec: consol-node-key-isolation-and-shared-context（需求 4.1；设计 §六.1、ADR-CNSC-001/003）。

本任务只做：`GET /api/consolidation/reports/{project_id}/{year}` 增可选 node_key；
缺省选当前树根；显式键经当前项目/年度企业树精确验证；非法键 / 无效年度 / 非合并项目明确拒绝。
节点金额实时计算（load_view_context → node_measures → consol_report_values）是任务 4.2，不在此测。

被测真实生产函数（禁 mock 替换被测函数本身）：
  - ``consol_note_scope.resolve_report_node_scope``  报表端点节点作用域解析（缺省默认根）
  - ``routers.consol_report.get_consol_report``       经真 FastAPI 请求验证入参与拒绝语义

企业树身份用 ``group`` 夹具真实构建（G⊃A⊃A1, G⊃B；G:consol 为根，A:consol 为子合并节点）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User, UserRole
from app.services.consol_note_scope import NodeScope, NoteScopeError, resolve_report_node_scope
from app.services.consol_tree_service import build_tree, find_node_by_key

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行）。
from tests.test_consol_push import (  # noqa: F401
    Y,
    db,
    factory,
    group,
)


@pytest_asyncio.fixture
async def tree_root(db, group):
    """真实构建 G 集团企业树根；断言根为 G:consol。"""
    root = await build_tree(db, group["G"].id)
    assert root is not None and root.node_key == "G:consol", "根节点应为 G:consol"
    return root


# ─────────────────────────── resolve_report_node_scope（§六.1；需求 4.1） ───────────────────────────


class TestResolveReportScope:
    @pytest.mark.asyncio
    async def test_omitted_node_key_defaults_to_tree_root(self, db, group, tree_root):
        """缺省（不传 node_key）⇒ 默认当前树的根合并节点 G:consol（设计 §六.1）。"""
        scope = await resolve_report_node_scope(db, group["G"].id, Y, node_key=None)
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "G:consol"
        assert scope.is_root_consol is True
        assert scope.year == Y

    @pytest.mark.asyncio
    async def test_explicit_root_key_validated(self, db, group, tree_root):
        scope = await resolve_report_node_scope(db, group["G"].id, Y, node_key="G:consol")
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "G:consol"
        assert scope.is_root_consol is True

    @pytest.mark.asyncio
    async def test_explicit_nonroot_consol_child_validated_not_root(self, db, group, tree_root):
        """A:consol 在树里但不是根 ⇒ NodeScope 且 is_root_consol=False（禁 ':consol' 后缀兜底）。"""
        child = find_node_by_key(tree_root, "A:consol")
        assert child is not None and child.role == "consol"
        scope = await resolve_report_node_scope(db, group["G"].id, Y, node_key="A:consol")
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "A:consol"
        assert scope.is_root_consol is False

    @pytest.mark.asyncio
    async def test_explicit_data_node_validated(self, db, group, tree_root):
        scope = await resolve_report_node_scope(db, group["G"].id, Y, node_key="B:subsidiary")
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "B:subsidiary"
        assert scope.is_root_consol is False

    @pytest.mark.asyncio
    async def test_illegal_key_rejected_400(self, db, group, tree_root):
        with pytest.raises(NoteScopeError) as exc:
            await resolve_report_node_scope(db, group["G"].id, Y, node_key="ZZ:consol")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_empty_string_rejected_400(self, db, group, tree_root):
        """空字符串是显式无效输入 —— 不降级成"省略默认根"。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_report_node_scope(db, group["G"].id, Y, node_key="")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_mismatched_year_rejected_400(self, db, group, tree_root):
        """显式年度与项目审计年度不一致 ⇒ 400，不跨年。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_report_node_scope(db, group["G"].id, Y - 1, node_key="G:consol")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_mismatched_year_rejected_even_without_node_key(self, db, group, tree_root):
        """缺省节点键也要校验年度：跨年 ⇒ 400（默认根不绕过年度校验）。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_report_node_scope(db, group["G"].id, Y - 1, node_key=None)
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_non_consol_project_rejected_404(self, db, group, tree_root):
        """单户项目不是合并项目 ⇒ 404（缺省节点键同样拒绝，不伪造根）。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_report_node_scope(db, group["B"].id, Y, node_key=None)
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_effective_year_falls_back_to_project_year(self, db, group, tree_root):
        """year=None ⇒ 取项目审计年度，默认根。"""
        scope = await resolve_report_node_scope(db, group["G"].id, None, node_key=None)
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "G:consol"
        assert scope.year == Y


# ─────────────────────────── 真 FastAPI 请求：入参与拒绝语义（需求 4.1） ───────────────────────────


def _make_app(db_session) -> FastAPI:
    from app.routers.consol_report import router

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        import uuid as _u
        return User(
            id=_u.UUID("00000000-0000-0000-0000-000000000001"),
            username="t_admin", email="a@t.com", hashed_password="x", role=UserRole.admin,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[require_project_access("readonly")] = _override_user
    return app


async def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


class TestEndpointNodeKeyParam:
    @pytest.mark.asyncio
    async def test_illegal_node_key_returns_400(self, db, group, tree_root):
        """显式非法 node_key ⇒ 400，且不降级成根、不读物化报表。"""
        app = _make_app(db)
        async with await _client(app) as client:
            resp = await client.get(
                f"/api/consolidation/reports/{group['G'].id}/{Y}",
                params={"report_type": "balance_sheet", "node_key": "ZZ:consol"},
            )
        assert resp.status_code == 400
        assert "ZZ:consol" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_node_key_returns_400(self, db, group, tree_root):
        app = _make_app(db)
        async with await _client(app) as client:
            resp = await client.get(
                f"/api/consolidation/reports/{group['G'].id}/{Y}",
                params={"report_type": "balance_sheet", "node_key": ""},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_non_consol_project_returns_404(self, db, group, tree_root):
        """单户项目 ⇒ 404（节点作用域校验先于报表读取）。"""
        app = _make_app(db)
        async with await _client(app) as client:
            resp = await client.get(
                f"/api/consolidation/reports/{group['B'].id}/{Y}",
                params={"report_type": "balance_sheet"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_default_root_passes_validation_then_reads_realtime(self, db, group, tree_root):
        """缺省节点键通过校验（默认根）后，进入**读时计算**路径（任务 4.2/4.3）返回 200 行数组。

        这证明：入参校验放行了合法默认根请求（没抛节点非法 400），随后按 node_key 实时计算
        （不再依赖项目级物化 FinancialReport，故不再 404「请先生成合并报表」）。
        """
        app = _make_app(db)
        async with await _client(app) as client:
            resp = await client.get(
                f"/api/consolidation/reports/{group['G'].id}/{Y}",
                params={"report_type": "balance_sheet"},
            )
        assert resp.status_code == 200, resp.text
        rows = {r["row_code"]: r for r in resp.json()}
        assert "BS-002" in rows and rows["BS-002"]["current_period_amount"] == "1400.00"

    @pytest.mark.asyncio
    async def test_valid_explicit_node_key_reads_realtime(self, db, group, tree_root):
        """显式合法节点键（非根子合并节点 A:consol）通过校验，进入读时计算，返回 200 该节点行值。"""
        app = _make_app(db)
        async with await _client(app) as client:
            resp = await client.get(
                f"/api/consolidation/reports/{group['G'].id}/{Y}",
                params={"report_type": "balance_sheet", "node_key": "A:consol"},
            )
        assert resp.status_code == 200, resp.text
        rows = {r["row_code"]: r for r in resp.json()}
        # A 子树（A_s + A1）货币资金 400.00
        assert rows["BS-002"]["current_period_amount"] == "400.00"
