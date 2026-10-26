"""合并试算一致性校验与手改接口删除（spec consol-autotree-linkage-closure R8.3 / R8.4）。

真 SQLite + 真 ORM 行 + 真 service；端点真发请求（ASGITransport），鉴权走真实实现（只替换当前用户与会话）。

- 判据按科目自然方向（``account_sign``）汇总借方性质与贷方性质合计：``consol_amount`` 是自然方向正数口径，
  旧判据按正负号分借贷 ⇒ 负债 / 权益 / 收入全被算进「借方」，平衡的试算表恒报不平；
- 路由曾漏 ``await`` ⇒ ``ConsistencyCheckResult(**协程)`` 恒 500；
- ``PUT /consolidation/trial/{trial_id}`` 已删除（派生数不允许手改，且旧实现 ``db.commit()`` 未 await，报成功却不保存）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consolidation_models import ConsolTrial
from app.models.core import Project

Y = 2025
D = Decimal

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _project(db) -> Project:
    p = Project(id=uuid.uuid4(), name=f"某集团_{Y}", client_name="某集团", company_code="G",
                report_scope="consolidated", audit_year=Y, status=ProjectStatus.execution)
    db.add(p)
    await db.commit()
    return p


async def _rows(db, project, rows):
    for code, name, amount in rows:
        db.add(ConsolTrial(project_id=project.id, year=Y, standard_account_code=code, account_name=name,
                           individual_sum=D(amount), consol_adjustment=D(0), consol_elimination=D(0),
                           consol_amount=D(amount), is_stale=False))
    await db.commit()


# 资产 1000 + 费用 200（借方性质）= 负债 300 + 权益 700 + 收入 200（贷方性质），全为正数
_BALANCED = [
    ("1001", "货币资金", "1000"), ("6401", "主营业务成本", "200"),
    ("2202", "应付账款", "300"), ("4001", "实收资本", "700"), ("6001", "主营业务收入", "200"),
]


class TestConsistencyCriteria:
    @pytest.mark.asyncio
    async def test_balanced_by_natural_direction(self, db):
        from app.services.consol_trial_service import check_trial_consistency

        p = await _project(db)
        await _rows(db, p, _BALANCED)
        res = await check_trial_consistency(db, p.id, Y)
        # 🔴 旧判据按正负号：借 2400 / 贷 0 ⇒ 恒不平
        assert (res["total_debit"], res["total_credit"]) == (D("1200.00"), D("1200.00"))
        assert res["is_balanced"] is True and res["difference"] == 0 and res["errors"] == []

    @pytest.mark.asyncio
    async def test_contra_asset_counts_as_credit_nature(self, db):
        from app.services.consol_trial_service import check_trial_consistency

        p = await _project(db)
        await _rows(db, p, [("1601", "固定资产", "500"), ("1602", "累计折旧", "100"), ("4001", "实收资本", "400")])
        res = await check_trial_consistency(db, p.id, Y)
        assert (res["total_debit"], res["total_credit"], res["is_balanced"]) == (D("500.00"), D("500.00"), True), \
            "累计折旧是贷方性质（与合并计算 account_sign 同源），不按科目首位当资产"

    @pytest.mark.asyncio
    async def test_unbalanced_and_empty_explained(self, db):
        from app.services.consol_trial_service import check_trial_consistency

        p = await _project(db)
        empty = await check_trial_consistency(db, p.id, Y)
        assert empty["is_balanced"] is True and "合并试算表为空" in empty["warnings"][0]
        await _rows(db, p, _BALANCED + [("1122", "应收账款", "50")])
        res = await check_trial_consistency(db, p.id, Y)
        assert res["is_balanced"] is False and res["difference"] == D("50.00")
        assert "相差 50.00" in res["errors"][0]


class _Admin:
    id = uuid.uuid4()
    username = "admin_t"
    role = UserRole.admin
    is_active = True
    is_deleted = False


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_consistency_endpoint_works_and_put_removed(self, db):
        from app.routers.consol_trial import router

        p = await _project(db)
        await _rows(db, p, _BALANCED)
        app = FastAPI()
        app.include_router(router)

        async def _db():
            yield db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: _Admin()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/consolidation/trial/consistency-check", params={"project_id": str(p.id), "year": Y})
            assert resp.status_code == 200, resp.text  # 🔴 旧路由漏 await ⇒ 500
            assert resp.json()["is_balanced"] is True
            trial_id = (await c.get("/api/consolidation/trial", params={"project_id": str(p.id), "year": Y})).json()[0]["id"]
            put = await c.put(f"/api/consolidation/trial/{trial_id}", params={"project_id": str(p.id)},
                              json={"consol_amount": "1"})
            assert put.status_code == 405, "手改合并试算行接口已删除"
        assert not any(getattr(r, "path", "") == "/api/consolidation/trial/{trial_id}" and "PUT" in getattr(r, "methods", set())
                       for r in router.routes)
