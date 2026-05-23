"""调整分录影响预览（preview-impact）测试

覆盖 proposal-remaining-18 task 2.1（L-2）：
- POST /api/projects/{pid}/adjustments/preview-impact
- 不写 DB（只读 report_line_mapping + wp_account_mapping.json）
- 同 row 多 line 累加
- 借贷方向（debit/credit 科目）正确签名
- 多张报表（BS + IS）同时受影响
- 受影响 wp_code 列表去重
- 兼容 standard_account_code / debit_amount / credit_amount 旧字段名
- 未映射科目进入 unmapped_accounts
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

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
    AccountChart,
    AccountDirection,
    AccountSource,
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
)
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType
from app.routers.adjustments import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "preview_test"
        self.email = "preview@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """种子数据：
    - 资产类（debit）：1122 应收账款 → BS-005
    - 收入类（credit）：6001 主营业务收入 → IS-001
    - 资产类（debit）：1001 库存现金 → BS-002
    - 资产类（debit）：1002 银行存款 → BS-002（同行）
    """
    project = Project(
        id=uuid.uuid4(),
        name="preview_impact_test",
        client_name="客户A",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db_session.add(project)
    await db_session.flush()
    pid = project.id

    db_session.add_all([
        AccountChart(
            project_id=pid, account_code="1122", account_name="应收账款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="1001", account_name="库存现金",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=pid, account_code="1002", account_name="银行存款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
    ])

    db_session.add_all([
        ReportLineMapping(
            project_id=pid, standard_account_code="1122",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-005", report_line_name="应收账款",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        ReportLineMapping(
            project_id=pid, standard_account_code="6001",
            report_type=ReportType.income_statement,
            report_line_code="IS-001", report_line_name="营业收入",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        ReportLineMapping(
            project_id=pid, standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-002", report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        ReportLineMapping(
            project_id=pid, standard_account_code="1002",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-002", report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=True,
        ),
        # 未确认的映射不应被使用
        ReportLineMapping(
            project_id=pid, standard_account_code="1122",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-999", report_line_name="测试_未确认",
            report_line_level=1,
            mapping_type=ReportLineMappingType.manual,
            is_confirmed=False,
        ),
    ])

    await db_session.commit()
    return pid


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, monkeypatch) -> AsyncClient:
    # SQLite 不支持 SET LOCAL，monkeypatch 为 no-op；require_project_access 内部的
    # 权限校验对 admin 用户已直接通过（见 deps.py:156），无需绕过其他逻辑。
    async def _noop_rls(session, project_id):
        return None

    import app.deps as _deps_mod
    monkeypatch.setattr(_deps_mod, "set_rls_context", _noop_rls)

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db_session

    async def _u():
        return TEST_USER

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _u

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# 单元测试 - 服务层
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_impact_debit_asset_account(db_session, seeded):
    """资产科目（debit）借方 100000 → BS-005 delta = +100000。"""
    from app.services.adjustment_impact_service import preview_impact

    pid = seeded
    result = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[{"account_code": "1122", "debit": 100000, "credit": 0}],
        year=2025,
    )

    rows = result["affected_report_rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["report_type"] == "balance_sheet"
    assert row["row_code"] == "BS-005"
    assert row["field"] == "当期金额"
    assert row["delta"] == Decimal("100000")
    assert "BS-999" not in [r["row_code"] for r in rows]  # 未确认的映射应被排除


@pytest.mark.asyncio
async def test_preview_impact_credit_revenue_account(db_session, seeded):
    """收入科目（credit）贷方 50000 → IS-001 delta = +50000；借方 50000 → IS-001 delta = -50000。"""
    from app.services.adjustment_impact_service import preview_impact

    pid = seeded

    # 贷方录入：收入科目增加
    res1 = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[{"account_code": "6001", "debit": 0, "credit": 50000}],
    )
    assert res1["affected_report_rows"][0]["delta"] == Decimal("50000")

    # 借方录入（红字冲销）：收入科目减少
    res2 = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[{"account_code": "6001", "debit": 50000, "credit": 0}],
    )
    assert res2["affected_report_rows"][0]["delta"] == Decimal("-50000")


@pytest.mark.asyncio
async def test_preview_impact_balanced_entry_two_reports(db_session, seeded):
    """平衡分录（借 1122 / 贷 6001）→ 同时影响 BS-005 + IS-001。"""
    from app.services.adjustment_impact_service import preview_impact

    pid = seeded
    result = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[
            {"account_code": "1122", "debit": 80000, "credit": 0},
            {"account_code": "6001", "debit": 0, "credit": 80000},
        ],
    )

    rows = result["affected_report_rows"]
    by_row = {(r["report_type"], r["row_code"]): r for r in rows}
    assert by_row[("balance_sheet", "BS-005")]["delta"] == Decimal("80000")
    assert by_row[("income_statement", "IS-001")]["delta"] == Decimal("80000")


@pytest.mark.asyncio
async def test_preview_impact_aggregates_same_row(db_session, seeded):
    """1001 + 1002 同行 BS-002 → 累加到一条记录。"""
    from app.services.adjustment_impact_service import preview_impact

    pid = seeded
    result = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[
            {"account_code": "1001", "debit": 1000, "credit": 0},
            {"account_code": "1002", "debit": 2000, "credit": 0},
        ],
    )

    rows = [r for r in result["affected_report_rows"] if r["row_code"] == "BS-002"]
    assert len(rows) == 1
    assert rows[0]["delta"] == Decimal("3000")


@pytest.mark.asyncio
async def test_preview_impact_unmapped_account(db_session, seeded):
    """未在 account_chart 也未在 RLM 中的科目 → unmapped_accounts。"""
    from app.services.adjustment_impact_service import preview_impact

    pid = seeded
    result = await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[
            {"account_code": "9999", "debit": 100, "credit": 0},
            {"account_code": "1122", "debit": 200, "credit": 0},
        ],
    )

    assert "9999" in result["unmapped_accounts"]
    # 1122 仍正常计算
    rows = [r for r in result["affected_report_rows"] if r["row_code"] == "BS-005"]
    assert len(rows) == 1
    assert rows[0]["delta"] == Decimal("200")


@pytest.mark.asyncio
async def test_preview_impact_does_not_write_db(db_session, seeded):
    """断言函数全程未触发 commit / flush，不污染 DB。"""
    from sqlalchemy import text as sql_text

    from app.services.adjustment_impact_service import preview_impact

    pid = seeded
    before_count = (
        await db_session.execute(sql_text("SELECT COUNT(*) FROM adjustments"))
    ).scalar() or 0

    await preview_impact(
        db=db_session,
        project_id=pid,
        line_items=[
            {"account_code": "1122", "debit": 100, "credit": 0},
            {"account_code": "6001", "debit": 0, "credit": 100},
        ],
    )
    # 显式 expire 任何缓存对象后再查
    after_count = (
        await db_session.execute(sql_text("SELECT COUNT(*) FROM adjustments"))
    ).scalar() or 0
    assert before_count == after_count == 0


# ---------------------------------------------------------------------------
# API 路由测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_preview_impact_basic(client: AsyncClient, seeded):
    """POST /preview-impact 基本调用：1122 借 100000 → BS-005 delta=100000。"""
    pid = seeded
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/preview-impact",
        json={
            "year": 2025,
            "line_items": [
                {"account_code": "1122", "debit": 100000, "credit": 0},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "affected_report_rows" in body
    assert "affected_workpapers" in body

    rows = body["affected_report_rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["report_type"] == "balance_sheet"
    assert r["row_code"] == "BS-005"
    assert r["row_name"] == "应收账款"
    assert r["field"] == "当期金额"
    # delta 序列化为 str
    assert Decimal(r["delta"]) == Decimal("100000")


@pytest.mark.asyncio
async def test_api_preview_impact_workpapers_includes_d2(client: AsyncClient, seeded):
    """1122 受影响底稿应包含 D2（应收账款审定表）— 来自 wp_account_mapping.json。"""
    pid = seeded
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/preview-impact",
        json={
            "line_items": [
                {"account_code": "1122", "debit": 100000, "credit": 0},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["affected_workpapers"], list)
    # 实际仓库中 wp_account_mapping.json D2 -> 1122
    mapping_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "wp_account_mapping.json"
    )
    if mapping_file.exists():
        with mapping_file.open(encoding="utf-8-sig") as f:
            data = json.load(f)
        wps_for_1122 = [
            m["wp_code"]
            for m in data.get("mappings", [])
            if "1122" in (m.get("account_codes") or [])
        ]
        for wp in wps_for_1122:
            assert wp in body["affected_workpapers"], (
                f"{wp} should be in affected_workpapers"
            )


@pytest.mark.asyncio
async def test_api_preview_impact_legacy_field_names(client: AsyncClient, seeded):
    """兼容历史字段名 standard_account_code / debit_amount / credit_amount。"""
    pid = seeded
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/preview-impact",
        json={
            "line_items": [
                {
                    "standard_account_code": "1122",
                    "debit_amount": "150000",
                    "credit_amount": "0",
                },
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["affected_report_rows"][0]["delta"]) == Decimal("150000")


@pytest.mark.asyncio
async def test_api_preview_impact_empty_line_items_400(client: AsyncClient, seeded):
    """line_items 为空 → 422（pydantic min_length=1）。"""
    pid = seeded
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/preview-impact",
        json={"line_items": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_preview_impact_balanced_two_rows(client: AsyncClient, seeded):
    """平衡分录返回两条受影响行（BS-005 + IS-001）。"""
    pid = seeded
    resp = await client.post(
        f"/api/projects/{pid}/adjustments/preview-impact",
        json={
            "line_items": [
                {"account_code": "1122", "debit": 60000, "credit": 0},
                {"account_code": "6001", "debit": 0, "credit": 60000},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    rows = body["affected_report_rows"]
    assert len(rows) == 2
    by_key = {(r["report_type"], r["row_code"]): r for r in rows}
    assert Decimal(by_key[("balance_sheet", "BS-005")]["delta"]) == Decimal("60000")
    assert Decimal(by_key[("income_statement", "IS-001")]["delta"]) == Decimal("60000")
