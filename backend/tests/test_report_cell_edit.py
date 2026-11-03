"""报表单元格编辑端点 ``PUT /api/projects/{pid}/reports/cell``（权益变动表 / 资产减值准备表格内编辑）。

spec excel-style-table-editing 5.4：前端把「双击弹输入框」改成格内编辑，提交时写本端点。
改造时发现本端点自 2026-06-12 起**每次调用都 500**：函数里给 ``sa`` 赋了值（新建行分支的
``sa: dict | None = None``），整个函数的 ``sa`` 就成了局部变量，开头 ``sa.select(...)`` 恒抛
``UnboundLocalError`` —— 原先的弹窗编辑从来没保存成功过。这里用真 SQLite + 真路由（ASGI）钉住：

- 权益表：``cy:`` / ``py:`` 列键写 ``source_accounts.eq_matrix[年度][后端列]``，合计列同时写本期金额；
- 减值表：列键写 ``source_accounts[列键]``（与导出 ``{{imp:CODE:列键}}`` 同一契约）；没有该行时新建；
- 鉴权：非成员 403。
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


class _User:
    def __init__(self, role: str) -> None:
        self.id = uuid.uuid4()
        self.username = f"cell_{role}"
        self.role = MagicMock()
        self.role.value = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def project(session: AsyncSession) -> Project:
    p = Project(id=uuid.uuid4(), name="【测试】报表格内编辑", client_name="测试客户", audit_period_end=date(2025, 12, 31))
    session.add(p)
    await session.commit()
    return p


def _client(session: AsyncSession, user: _User) -> AsyncClient:
    from app.routers.reports import line_composition_router

    app = FastAPI()
    app.include_router(line_composition_router)

    async def _db():
        yield session

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _row(session: AsyncSession, project_id: uuid.UUID, report_type: FinancialReportType, code: str):
    """按列取值（不经 ORM 实例：端点在同一会话里新建的行，读属性会触发异步懒加载）。"""
    r = await session.execute(select(
        FinancialReport.year, FinancialReport.current_period_amount, FinancialReport.source_accounts,
    ).where(
        FinancialReport.project_id == project_id,
        FinancialReport.report_type == report_type,
        FinancialReport.row_code == code,
    ))
    return r.one()


@pytest.mark.asyncio
async def test_equity_cell_writes_eq_matrix_both_years(session, project) -> None:
    session.add(FinancialReport(
        project_id=project.id, year=2025, report_type=FinancialReportType.equity_statement,
        row_code="EQ-005", row_name="综合收益总额", source_accounts={"eq_matrix": {"current_year": {"share_capital": 1}}},
    ))
    await session.commit()
    async with _client(session, _User("admin")) as c:
        url = f"/api/projects/{project.id}/reports/cell"
        params = {"year": 2025, "report_type": "equity_statement"}
        r1 = await c.put(url, params=params, json={"row_code": "EQ-005", "column_key": "cy:oci", "value": 123.45, "year_key": "current_year"})
        r2 = await c.put(url, params=params, json={"row_code": "EQ-005", "column_key": "py:paid_in_capital", "value": 7, "year_key": "prior_year"})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    row = await _row(session, project.id, FinancialReportType.equity_statement, "EQ-005")
    matrix = row.source_accounts["eq_matrix"]
    assert matrix["current_year"] == {"share_capital": 1, "other_comprehensive_income": 123.45}
    assert matrix["prior_year"] == {"share_capital": 7}


@pytest.mark.asyncio
async def test_equity_total_cell_also_sets_current_amount(session, project) -> None:
    session.add(FinancialReport(
        project_id=project.id, year=2025, report_type=FinancialReportType.equity_statement, row_code="EQ-009",
    ))
    await session.commit()
    async with _client(session, _User("admin")) as c:
        r = await c.put(f"/api/projects/{project.id}/reports/cell", params={"year": 2025, "report_type": "equity_statement"},
                        json={"row_code": "EQ-009", "column_key": "cy:total", "value": 500, "year_key": "current_year"})
    assert r.status_code == 200, r.text
    row = await _row(session, project.id, FinancialReportType.equity_statement, "EQ-009")
    assert float(row.current_period_amount) == 500
    assert row.source_accounts["eq_matrix"]["current_year"]["total_equity"] == 500


@pytest.mark.asyncio
async def test_impairment_cell_uses_export_column_key_and_creates_row(session, project) -> None:
    session.add(FinancialReport(
        project_id=project.id, year=2025, report_type=FinancialReportType.impairment_provision,
        row_code="IMP-001", row_name="坏账准备", source_accounts={"reversal": 3},
    ))
    await session.commit()
    async with _client(session, _User("admin")) as c:
        url = f"/api/projects/{project.id}/reports/cell"
        # 年度照前端传（不传时端点按项目审计年度取，那条查询是 PG 专用 SQL，SQLite 跑不了）
        params = {"year": 2025, "report_type": "impairment_provision"}
        r1 = await c.put(url, params=params, json={"row_code": "IMP-001", "column_key": "provision", "value": 40})
        r2 = await c.put(url, params=params, json={"row_code": "IMP-002", "column_key": "write_off", "value": 5})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert (await _row(session, project.id, FinancialReportType.impairment_provision, "IMP-001")).source_accounts == {"reversal": 3, "provision": 40}
    created = await _row(session, project.id, FinancialReportType.impairment_provision, "IMP-002")
    assert created.year == 2025
    assert created.source_accounts == {"write_off": 5}


@pytest.mark.asyncio
async def test_non_member_is_forbidden(session, project) -> None:
    async with _client(session, _User("auditor")) as c:
        r = await c.put(f"/api/projects/{project.id}/reports/cell", params={"year": 2025, "report_type": "impairment_provision"},
                        json={"row_code": "IMP-001", "column_key": "provision", "value": 1})
    assert r.status_code == 403
    rows = (await session.execute(select(FinancialReport))).scalars().all()
    assert rows == []


def test_handler_has_no_local_sa() -> None:
    """钉住根因：处理函数里 ``sa`` 不能是局部变量（否则开头的 ``sa.select`` 恒抛 UnboundLocalError）。"""
    from app.routers.reports import update_report_cell

    assert "sa" not in update_report_cell.__code__.co_varnames
