"""附注生成引擎 + 校验引擎 + API 路由测试

Validates: Requirements 4.2-4.10, 5.1-5.5, 8.1
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    NoteValidationResult,
    ReportConfig,
)
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_validation_engine import (
    NoteValidationEngine,
    validate_balance,
    validate_sub_item,
)
from app.services.report_config_service import ReportConfigService
from app.services.report_engine import ReportEngine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建测试数据：项目 + 试算表 + 报表配置 + 已生成报表"""
    # Project
    project = Project(
        id=FAKE_PROJECT_ID,
        name="附注测试_2025",
        client_name="附注测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Trial balance data — minimal set matching seed templates
    tb_data = [
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("40000")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("800000")),
        ("1012", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        ("1122", "应收账款", AccountCategory.asset, Decimal("300000"), Decimal("250000")),
        ("1401", "存货-原材料", AccountCategory.asset, Decimal("500000"), Decimal("400000")),
        ("1601", "固定资产原值", AccountCategory.asset, Decimal("2000000"), Decimal("1800000")),
        ("1602", "累计折旧", AccountCategory.asset, Decimal("500000"), Decimal("400000")),
        ("2001", "短期借款", AccountCategory.liability, Decimal("500000"), Decimal("400000")),
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("3000000"), Decimal("0")),
    ]

    for code, name, cat, audited, opening in tb_data:
        db_session.add(TrialBalance(
            project_id=FAKE_PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code=code,
            account_name=name,
            account_category=cat,
            unadjusted_amount=audited,
            audited_amount=audited,
            opening_balance=opening,
        ))

    await db_session.flush()

    # Load seed report configs and generate reports
    svc = ReportConfigService(db_session)
    await svc.load_seed_data()
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    return FAKE_PROJECT_ID


# ===== DisclosureEngine 测试 =====


@pytest.mark.asyncio
async def test_generate_notes(db_session: AsyncSession, seeded_db):
    """生成附注初稿"""
    engine = DisclosureEngine(db_session)
    results = await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    assert len(results) == 6  # 6 templates in seed data
    sections = [r["note_section"] for r in results]
    assert "五、1" in sections
    assert "五、6" in sections


@pytest.mark.asyncio
async def test_generate_notes_table_data(db_session: AsyncSession, seeded_db):
    """附注表格数据从试算表取数"""
    engine = DisclosureEngine(db_session)
    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # Check 货币资金 note
    note = await engine.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    assert note is not None
    assert note.table_data is not None

    rows = note.table_data["rows"]
    # 库存现金 = 50000
    assert rows[0]["label"] == "库存现金"
    assert rows[0]["values"][0] == 50000.0
    # 银行存款 = 1000000
    assert rows[1]["label"] == "银行存款"
    assert rows[1]["values"][0] == 1000000.0
    # 合计 = 1150000
    total_row = [r for r in rows if r["is_total"]][0]
    assert total_row["values"][0] == 1150000.0


@pytest.mark.asyncio
async def test_generate_notes_idempotent(db_session: AsyncSession, seeded_db):
    """重复生成不会创建重复记录"""
    engine = DisclosureEngine(db_session)
    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    import sqlalchemy as sa
    result1 = await db_session.execute(
        sa.select(sa.func.count()).select_from(DisclosureNote).where(
            DisclosureNote.project_id == FAKE_PROJECT_ID,
            DisclosureNote.year == 2025,
        )
    )
    count1 = result1.scalar()

    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    result2 = await db_session.execute(
        sa.select(sa.func.count()).select_from(DisclosureNote).where(
            DisclosureNote.project_id == FAKE_PROJECT_ID,
            DisclosureNote.year == 2025,
        )
    )
    count2 = result2.scalar()
    assert count1 == count2


@pytest.mark.asyncio
async def test_get_notes_tree(db_session: AsyncSession, seeded_db):
    """获取附注目录树"""
    engine = DisclosureEngine(db_session)
    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    tree = await engine.get_notes_tree(FAKE_PROJECT_ID, 2025)
    assert len(tree) == 6
    assert tree[0]["note_section"] == "五、1"
    assert tree[0]["section_title"] == "货币资金"


@pytest.mark.asyncio
async def test_update_note(db_session: AsyncSession, seeded_db):
    """更新附注章节"""
    engine = DisclosureEngine(db_session)
    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    note = await engine.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    assert note is not None

    updated = await engine.update_note(
        note.id,
        text_content="测试文本内容",
        status=NoteStatus.confirmed,
    )
    await db_session.commit()

    assert updated is not None
    assert updated.text_content == "测试文本内容"
    assert updated.status == NoteStatus.confirmed


@pytest.mark.asyncio
async def test_update_note_values(db_session: AsyncSession, seeded_db):
    """增量更新附注数值"""
    engine = DisclosureEngine(db_session)
    await engine.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # Modify trial balance
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == FAKE_PROJECT_ID,
            TrialBalance.year == 2025,
            TrialBalance.standard_account_code == "1001",
        )
    )
    tb_row = result.scalar_one()
    tb_row.audited_amount = Decimal("60000")  # was 50000
    await db_session.flush()

    updated = await engine.update_note_values(
        FAKE_PROJECT_ID, 2025, changed_accounts=["1001"],
    )
    await db_session.commit()

    assert updated >= 1

    # Verify updated value
    note = await engine.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    rows = note.table_data["rows"]
    assert rows[0]["values"][0] == 60000.0  # 库存现金 updated


# ===== NoteValidationEngine 测试 =====


@pytest.mark.asyncio
async def test_validate_all_no_errors(db_session: AsyncSession, seeded_db):
    """校验通过：附注数据与报表一致"""
    de = DisclosureEngine(db_session)
    await de.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    nve = NoteValidationEngine(db_session)
    result = await nve.validate_all(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # 货币资金 note total should match BS-002 report amount
    # Both should be 1150000, so no balance errors for 货币资金
    balance_errors = [
        f for f in result["findings"]
        if f["check_type"] == "balance" and f["note_section"] == "五、1"
    ]
    assert len(balance_errors) == 0


@pytest.mark.asyncio
async def test_validate_balance_mismatch(db_session: AsyncSession, seeded_db):
    """余额核对：附注与报表不一致时报错"""
    de = DisclosureEngine(db_session)
    await de.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # Manually modify note total to create mismatch
    note = await de.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    table_data = note.table_data
    # Change total row value
    for row in table_data["rows"]:
        if row["is_total"]:
            row["values"][0] = 999999.0
    note.table_data = table_data
    await db_session.flush()

    nve = NoteValidationEngine(db_session)
    result = await nve.validate_all(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    balance_errors = [
        f for f in result["findings"]
        if f["check_type"] == "balance" and f["note_section"] == "五、1"
    ]
    assert len(balance_errors) == 1
    assert balance_errors[0]["severity"] == "error"


@pytest.mark.asyncio
async def test_validate_sub_item_mismatch(db_session: AsyncSession, seeded_db):
    """其中项校验：明细行之和 ≠ 合计行时报错"""
    de = DisclosureEngine(db_session)
    await de.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # Manually modify a detail row to create sub_item mismatch
    note = await de.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    table_data = note.table_data
    # Change 库存现金 value but keep total the same
    table_data["rows"][0]["values"][0] = 99999.0
    note.table_data = table_data
    await db_session.flush()

    nve = NoteValidationEngine(db_session)
    result = await nve.validate_all(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    sub_item_errors = [
        f for f in result["findings"]
        if f["check_type"] == "sub_item" and f["note_section"] == "五、1"
    ]
    assert len(sub_item_errors) >= 1


@pytest.mark.asyncio
async def test_confirm_finding(db_session: AsyncSession, seeded_db):
    """确认校验发现"""
    de = DisclosureEngine(db_session)
    await de.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    # Create a mismatch to get a finding
    note = await de.get_note_detail(FAKE_PROJECT_ID, 2025, "五、1")
    table_data = note.table_data
    for row in table_data["rows"]:
        if row["is_total"]:
            row["values"][0] = 999999.0
    note.table_data = table_data
    await db_session.flush()

    nve = NoteValidationEngine(db_session)
    result = await nve.validate_all(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    validation_id = uuid.UUID(result["id"])
    success = await nve.confirm_finding(validation_id, 0, "已核实，差异可接受")
    await db_session.commit()

    assert success is True

    # Verify finding is confirmed
    latest = await nve.get_latest_results(FAKE_PROJECT_ID, 2025)
    assert latest.findings[0]["confirmed"] is True
    assert latest.findings[0]["confirm_reason"] == "已核实，差异可接受"


@pytest.mark.asyncio
async def test_get_latest_results(db_session: AsyncSession, seeded_db):
    """获取最新校验结果"""
    de = DisclosureEngine(db_session)
    await de.generate_notes(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    nve = NoteValidationEngine(db_session)
    await nve.validate_all(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    latest = await nve.get_latest_results(FAKE_PROJECT_ID, 2025)
    assert latest is not None
    assert latest.project_id == FAKE_PROJECT_ID
    assert latest.year == 2025


# ===== API 路由测试 =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端"""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_generate_notes(client: AsyncClient):
    """POST /api/disclosure-notes/generate"""
    resp = await client.post(
        "/api/disclosure-notes/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "template_type": "soe",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["note_count"] == 6


@pytest.mark.asyncio
async def test_api_get_notes_tree(client: AsyncClient):
    """GET /api/disclosure-notes/{project_id}/{year}"""
    # First generate
    await client.post(
        "/api/disclosure-notes/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "template_type": "soe",
        },
    )

    resp = await client.get(
        f"/api/disclosure-notes/{FAKE_PROJECT_ID}/2025"
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert len(items) == 6


@pytest.mark.asyncio
async def test_api_get_note_detail(client: AsyncClient):
    """GET /api/disclosure-notes/{project_id}/{year}/{note_section}"""
    await client.post(
        "/api/disclosure-notes/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "template_type": "soe",
        },
    )

    # URL-encode the note_section "五、1"
    import urllib.parse
    section = urllib.parse.quote("五、1")
    resp = await client.get(
        f"/api/disclosure-notes/{FAKE_PROJECT_ID}/2025/{section}"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["section_title"] == "货币资金"


@pytest.mark.asyncio
async def test_api_validate_notes(client: AsyncClient):
    """POST /api/disclosure-notes/{project_id}/{year}/validate"""
    await client.post(
        "/api/disclosure-notes/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "template_type": "soe",
        },
    )

    resp = await client.post(
        f"/api/disclosure-notes/{FAKE_PROJECT_ID}/2025/validate"
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert "findings" in result
    assert "error_count" in result


@pytest.mark.asyncio
async def test_api_get_validation_results(client: AsyncClient):
    """GET /api/disclosure-notes/{project_id}/{year}/validation-results"""
    # Generate + validate first
    await client.post(
        "/api/disclosure-notes/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "template_type": "soe",
        },
    )
    await client.post(
        f"/api/disclosure-notes/{FAKE_PROJECT_ID}/2025/validate"
    )

    resp = await client.get(
        f"/api/disclosure-notes/{FAKE_PROJECT_ID}/2025/validation-results"
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_notes_tree_not_found(client: AsyncClient):
    """GET 未生成的附注返回 404"""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/api/disclosure-notes/{fake_id}/2025"
    )
    assert resp.status_code == 404
