"""端点级回归：两个数据链端点此前每次调用都 NameError → 500（漏 import ``select``）。

🔴 缺陷（2026-09-29 ruff F821 现扫发现，零测试覆盖故长期未暴露）：
- ``PUT  /api/projects/{pid}/account-chart/batch-update``（科目表批量编辑）
  → 函数体 ``select(AccountChart)`` 未 import ⇒ 500；其后的 ACCOUNT_MAPPING_CHANGED 也从未发出
- ``GET/PUT /api/report-config/tb-detail-formulas/{pid}``（公式管理中心「试算平衡表 > 科目明细」
  加载 / 保存）→ ``_tb_get_project_or_404`` 里 ``select`` 未 import ⇒ 两个端点都 500

测试方式：TestClient 真发请求（只 override ``get_current_user`` / ``get_db``，让真实权限依赖
``require_project_access`` / ``require_role`` 照常执行），不是只测 service —— 只测 service 正是
这类缺陷漏网的原因（端点装配 / 依赖链 / 响应信封全在盲区）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, UserRole  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
)
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pid = uuid.uuid4()
    admin = User(
        id=uuid.uuid4(), username="admin_t", email="a@t.local",
        hashed_password="x", role=UserRole.admin, is_active=True,
    )
    async with factory() as db:
        db.add(admin)
        db.add(Project(
            id=pid, name="端点回归项目_2025", client_name="测试客户",
            project_type=ProjectType.annual, status=ProjectStatus.created, audit_year=2025,
        ))
        db.add(AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.client,
        ))
        await db.commit()

    from app.routers.account_chart import router as account_chart_router
    from app.routers.report_config import router as report_config_router

    app = FastAPI()
    app.include_router(account_chart_router)
    app.include_router(report_config_router)

    async def _db():
        async with factory() as s:
            yield s

    async def _user():
        return admin

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory, pid
    await engine.dispose()


@pytest.mark.asyncio
async def test_account_chart_batch_update_no_longer_500(env):
    client, factory, pid = env
    r = await client.put(
        f"/api/projects/{pid}/account-chart/batch-update",
        json={"updates": [{"account_code": "1001", "account_name": "现金（改）"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1, "total": 1}
    async with factory() as db:
        name = (await db.execute(
            select(AccountChart.account_name).where(AccountChart.project_id == pid)
        )).scalar_one()
    assert name == "现金（改）", "端点返回 200 但未落库"


@pytest.mark.asyncio
async def test_tb_detail_formulas_roundtrip(env):
    client, factory, pid = env
    empty = await client.get(f"/api/report-config/tb-detail-formulas/{pid}")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"overrides": {}, "added": []}

    body = {
        "overrides": {"1001": {"row_code": "1001", "formula": "TB('1001','期末余额')"}},
        "added": [{"row_code": "X01", "row_name": "自定义行", "formula": "TB('1002','期末余额')"}],
    }
    saved = await client.put(f"/api/report-config/tb-detail-formulas/{pid}", json=body)
    assert saved.status_code == 200, saved.text

    again = await client.get(f"/api/report-config/tb-detail-formulas/{pid}")
    assert again.status_code == 200
    data = again.json()
    assert data["overrides"]["1001"]["formula"] == "TB('1001','期末余额')"
    assert [a["row_code"] for a in data["added"]] == ["X01"]


@pytest.mark.asyncio
async def test_tb_detail_formulas_unknown_project_is_404_not_500(env):
    client, _factory, _pid = env
    r = await client.get(f"/api/report-config/tb-detail-formulas/{uuid.uuid4()}")
    assert r.status_code == 404
