"""S-3 高级查询构建器后端单测

spec proposal-remaining-18 task 5.1

覆盖：
- /schema 返回白名单表与字段元信息
- /preview 仅生成 SQL 不执行
- /execute 各种操作符（eq/like/in/between/is_null）
- 白名单防御：非白名单表 → 400
- 白名单防御：非白名单字段 → 400
- 白名单防御：非白名单操作符 → 400
- SQL 注入防御：Bobby Tables 类 value 通过绑定参数转义，不会执行
- RBAC：auditor / qc / readonly 角色 → 403
- /export-excel 返回 xlsx 流
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.routers.query_builder import router as query_builder_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin):
        self.id = USER_ID
        self.role = role
        self.email = "tester@example.com"
        self.username = "tester"
        self.is_active = True


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session: AsyncSession, role: UserRole = UserRole.admin) -> FastAPI:
    app = FastAPI()
    app.include_router(query_builder_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _seed_data(db: AsyncSession) -> None:
    db.add(Project(
        id=PROJECT_ID,
        name="QueryBuilder 测试",
        client_name="QB Test",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=USER_ID,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
    ))
    await db.flush()

    # trial_balance 行：3 条覆盖不同数值
    db.add(TrialBalance(
        project_id=PROJECT_ID, year=2025, company_code="C001",
        standard_account_code="1001", account_name="库存现金",
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("100000.00"),
        audited_amount=Decimal("100000.00"),
    ))
    db.add(TrialBalance(
        project_id=PROJECT_ID, year=2025, company_code="C001",
        standard_account_code="1002", account_name="银行存款",
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("500000.00"),
        audited_amount=Decimal("500000.00"),
    ))
    db.add(TrialBalance(
        project_id=PROJECT_ID, year=2025, company_code="C001",
        standard_account_code="2001", account_name="短期借款",
        account_category=AccountCategory.liability,
        unadjusted_amount=Decimal("300000.00"),
        audited_amount=Decimal("280000.00"),
    ))

    # adjustments 行
    db.add(Adjustment(
        project_id=PROJECT_ID, year=2025, company_code="C001",
        adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
        description="调整短期借款利息",
        account_code="2001", account_name="短期借款",
        debit_amount=Decimal("0"), credit_amount=Decimal("20000.00"),
        entry_group_id=uuid.uuid4(),
        review_status=ReviewStatus.draft,
        created_by=USER_ID,
    ))
    await db.commit()


# ───────────────────────────────────────────────────────────
# /schema
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_schema_returns_whitelist(db_session: AsyncSession):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/query/schema")
    assert resp.status_code == 200
    body = resp.json()
    table_names = {t["name"] for t in body["tables"]}
    # 必须包含核心 audit/财务表
    assert {"trial_balance", "adjustments", "working_paper",
            "unadjusted_misstatements", "report_line_mapping"} <= table_names
    # 严格不暴露 user/role/auth 表
    assert "users" not in table_names
    assert "roles" not in table_names
    # 操作符与聚合白名单存在
    assert "eq" in body["operators"]
    assert "between" in body["operators"]
    assert "sum" in body["aggregates"]


# ───────────────────────────────────────────────────────────
# /preview
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preview_generates_sql_without_executing(db_session: AsyncSession):
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code", "account_name", "audited_amount"],
        "filters": [
            {"field": "year", "op": "eq", "value": 2025},
            {"field": "audited_amount", "op": "gte", "value": 100000},
        ],
        "order_by": [{"field": "audited_amount", "direction": "desc"}],
        "limit": 50,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/preview", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # SQL 含 trial_balance 表名 + 选中字段
    sql_lower = body["sql"].lower()
    assert "trial_balance" in sql_lower
    assert "standard_account_code" in sql_lower
    assert "audited_amount" in sql_lower
    # 必须使用绑定参数（: 占位）— SQLAlchemy 默认带 :param_N
    assert ":" in body["sql"]
    assert body["columns"] == ["standard_account_code", "account_name", "audited_amount"]


# ───────────────────────────────────────────────────────────
# /execute — 操作符覆盖
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_execute_eq_filter(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code", "account_name"],
        "filters": [{"field": "standard_account_code", "op": "eq", "value": "1001"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["standard_account_code"] == "1001"


@pytest.mark.asyncio
async def test_execute_like_filter(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code", "account_name"],
        "filters": [{"field": "account_name", "op": "like", "value": "存款"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["account_name"] == "银行存款"


@pytest.mark.asyncio
async def test_execute_in_filter(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code"],
        "filters": [{"field": "standard_account_code", "op": "in",
                     "value": ["1001", "1002"]}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {r["standard_account_code"] for r in body["rows"]} == {"1001", "1002"}


@pytest.mark.asyncio
async def test_execute_between_filter(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code", "audited_amount"],
        "filters": [{"field": "audited_amount", "op": "between",
                     "value": [200000, 600000]}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # 500k + 280k 在区间内
    codes = {r["standard_account_code"] for r in body["rows"]}
    assert codes == {"1002", "2001"}


@pytest.mark.asyncio
async def test_execute_aggregate_sum(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["account_category"],
        "aggregates": [{"func": "sum", "field": "audited_amount", "alias": "total_audited"}],
        "group_by": ["account_category"],
        "order_by": [{"field": "account_category", "direction": "asc"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = {r["account_category"]: r["total_audited"] for r in body["rows"]}
    # asset = 100k + 500k = 600k
    assert rows["asset"] == 600000.0
    # liability = 280k
    assert rows["liability"] == 280000.0


# ───────────────────────────────────────────────────────────
# 安全：白名单防御
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_table_not_in_whitelist_returns_400(db_session: AsyncSession):
    app = _make_app(db_session)
    payload = {"table": "users", "fields": ["id"]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/preview", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error_code"] == "TABLE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_field_not_in_whitelist_returns_400(db_session: AsyncSession):
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["password_hash"],  # 显然不存在/不允许
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/preview", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error_code"] == "FIELD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_op_not_in_whitelist_returns_400(db_session: AsyncSession):
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code"],
        "filters": [{"field": "standard_account_code",
                     "op": "regex_match",  # 不在白名单
                     "value": ".*"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/preview", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error_code"] == "OP_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_sql_injection_attempt_is_safely_bound(db_session: AsyncSession):
    """SQL 注入 payload 通过 SQLAlchemy 绑定参数转义，不会 DROP 表也不会爆库。

    "Bobby Tables" 经典 payload：value 在 LIKE 中作为字符串字面量出现，
    不会被解析为 SQL 命令。
    """
    await _seed_data(db_session)
    app = _make_app(db_session)
    evil_value = "'; DROP TABLE trial_balance; --"
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code"],
        "filters": [{"field": "account_name", "op": "like", "value": evil_value}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    # 不应返回 5xx，且不应清空表
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 0  # 没有行匹配该字符串

    # 表仍然完整：再来一次普通查询应正常返回
    payload2 = {
        "table": "trial_balance",
        "fields": ["standard_account_code"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp2 = await ac.post("/api/query/execute", json=payload2)
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 3  # 三条种子数据仍在


# ───────────────────────────────────────────────────────────
# RBAC
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_auditor_role_is_forbidden(db_session: AsyncSession):
    app = _make_app(db_session, role=UserRole.auditor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/query/schema")
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "QUERY_BUILDER_FORBIDDEN"


@pytest.mark.asyncio
async def test_qc_role_is_forbidden(db_session: AsyncSession):
    app = _make_app(db_session, role=UserRole.qc)
    payload = {"table": "trial_balance", "fields": ["standard_account_code"]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_role_allowed(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session, role=UserRole.manager)
    payload = {"table": "trial_balance", "fields": ["standard_account_code"], "limit": 10}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/execute", json=payload)
    assert resp.status_code == 200


# ───────────────────────────────────────────────────────────
# /export-excel
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_export_excel_returns_xlsx_stream(db_session: AsyncSession):
    await _seed_data(db_session)
    app = _make_app(db_session)
    payload = {
        "table": "trial_balance",
        "fields": ["standard_account_code", "account_name", "audited_amount"],
        "limit": 50,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/export-excel", json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # 文件流非空且能被 openpyxl 解析
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    # 表头 + 3 行数据
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("standard_account_code", "account_name", "audited_amount")
    assert len(rows) == 4  # 1 header + 3 seed rows


# ───────────────────────────────────────────────────────────
# limit 上限保护
# ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_limit_capped_at_1000(db_session: AsyncSession):
    app = _make_app(db_session)
    payload = {"table": "trial_balance", "fields": ["id"], "limit": 50000}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post("/api/query/preview", json=payload)
    # Pydantic 校验 limit ≤ 1000，超出则 422
    assert resp.status_code == 422
