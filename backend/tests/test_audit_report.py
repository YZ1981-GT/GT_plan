"""审计报告模板管理测试

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    TrialBalance,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    AuditReport,
    AuditReportTemplate,
    CompanyType,
    FinancialReport,
    FinancialReportType,
    OpinionType,
    ReportStatus,
)
from app.services.audit_report_service import AuditReportService
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
    """创建完整测试数据：项目 + 试算表 + 报表配置 + 报表数据 + 审计报告模板"""
    # Project
    project = Project(
        id=FAKE_PROJECT_ID,
        name="审计报告测试_2025",
        client_name="审计报告测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    # Minimal trial balance data
    tb_data = [
        ("1001", "库存现金", AccountCategory.asset, Decimal("50000"), Decimal("40000")),
        ("1002", "银行存款", AccountCategory.asset, Decimal("1000000"), Decimal("800000")),
        ("1012", "其他货币资金", AccountCategory.asset, Decimal("100000"), Decimal("80000")),
        ("4001", "实收资本", AccountCategory.equity, Decimal("2000000"), Decimal("2000000")),
        ("6001", "主营业务收入", AccountCategory.revenue, Decimal("3000000"), Decimal("0")),
        ("6401", "主营业务成本", AccountCategory.expense, Decimal("2000000"), Decimal("0")),
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

    # Load report configs and generate reports
    config_svc = ReportConfigService(db_session)
    await config_svc.load_seed_data()
    engine = ReportEngine(db_session)
    await engine.generate_all_reports(FAKE_PROJECT_ID, 2025)

    # Load audit report templates
    svc = AuditReportService(db_session)
    await svc.load_seed_templates()

    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== 模板加载测试 =====


@pytest.mark.asyncio
async def test_load_seed_templates(db_session: AsyncSession):
    """加载审计报告模板种子数据"""
    svc = AuditReportService(db_session)
    count = await svc.load_seed_templates()
    await db_session.commit()
    assert count > 0


@pytest.mark.asyncio
async def test_load_seed_templates_idempotent(db_session: AsyncSession):
    """重复加载不会创建重复记录"""
    svc = AuditReportService(db_session)
    count1 = await svc.load_seed_templates()
    await db_session.commit()
    count2 = await svc.load_seed_templates()
    await db_session.commit()
    assert count1 == count2


@pytest.mark.asyncio
async def test_get_templates(db_session: AsyncSession, seeded_db):
    """获取模板列表"""
    svc = AuditReportService(db_session)
    templates = await svc.get_templates()
    assert len(templates) > 0


@pytest.mark.asyncio
async def test_get_templates_filtered(db_session: AsyncSession, seeded_db):
    """按意见类型筛选模板"""
    svc = AuditReportService(db_session)
    templates = await svc.get_templates(
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
    )
    assert len(templates) == 7  # 7 sections for unqualified non_listed
    section_names = [t.section_name for t in templates]
    assert "审计意见段" in section_names
    assert "审计师责任段" in section_names


# ===== 报告生成测试 =====


@pytest.mark.asyncio
async def test_generate_report_unqualified(db_session: AsyncSession, seeded_db):
    """生成标准无保留意见审计报告"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    assert report is not None
    assert report.opinion_type == OpinionType.unqualified
    assert report.company_type == CompanyType.non_listed
    assert report.status == ReportStatus.draft
    assert report.paragraphs is not None
    assert "审计意见段" in report.paragraphs
    assert "审计师责任段" in report.paragraphs
    assert len(report.paragraphs) == 7


@pytest.mark.asyncio
async def test_generate_report_fills_placeholders(db_session: AsyncSession, seeded_db):
    """生成报告时占位符被替换"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    opinion_text = report.paragraphs["审计意见段"]
    # {audit_period} should be replaced
    assert "2025年12月31日" in opinion_text
    # {entity_name} should be replaced with placeholder
    assert "[被审计单位名称]" in opinion_text


@pytest.mark.asyncio
async def test_generate_report_financial_data(db_session: AsyncSession, seeded_db):
    """生成报告时自动填充财务数据"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    assert report.financial_data is not None
    assert "total_revenue" in report.financial_data
    assert "net_profit" in report.financial_data


@pytest.mark.asyncio
async def test_generate_report_qualified(db_session: AsyncSession, seeded_db):
    """生成保留意见审计报告（使用 unqualified 模板补充缺失段落）"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.qualified, CompanyType.non_listed,
    )
    await db_session.commit()

    assert report.opinion_type == OpinionType.qualified
    assert "审计意见段" in report.paragraphs
    # Should have supplemented sections from unqualified template
    assert "管理层责任段" in report.paragraphs
    # Opinion text should mention 保留意见
    assert "保留意见" in report.paragraphs["审计意见段"]


@pytest.mark.asyncio
async def test_generate_report_idempotent(db_session: AsyncSession, seeded_db):
    """重复生成不会创建重复记录"""
    svc = AuditReportService(db_session)
    report1 = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    report2 = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.qualified, CompanyType.non_listed,
    )
    await db_session.commit()

    assert report1.id == report2.id
    assert report2.opinion_type == OpinionType.qualified


# ===== 段落编辑测试 =====


@pytest.mark.asyncio
async def test_update_paragraph(db_session: AsyncSession, seeded_db):
    """更新审计报告段落"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    updated = await svc.update_paragraph(
        report.id, "审计意见段", "自定义审计意见内容"
    )
    await db_session.commit()

    assert updated is not None
    assert updated.paragraphs["审计意见段"] == "自定义审计意见内容"


@pytest.mark.asyncio
async def test_update_paragraph_not_found(db_session: AsyncSession, seeded_db):
    """更新不存在的报告返回 None"""
    svc = AuditReportService(db_session)
    result = await svc.update_paragraph(uuid.uuid4(), "审计意见段", "test")
    assert result is None


# ===== 财务数据刷新测试 =====


@pytest.mark.asyncio
async def test_refresh_financial_data(db_session: AsyncSession, seeded_db):
    """刷新审计报告财务数据"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    refreshed = await svc.refresh_financial_data(FAKE_PROJECT_ID, 2025)
    await db_session.commit()

    assert refreshed is not None
    assert refreshed.financial_data is not None


# ===== KAM 校验测试 =====


@pytest.mark.asyncio
async def test_finalize_listed_without_kam_fails(db_session: AsyncSession, seeded_db):
    """上市公司 finalize 时缺少 KAM 应失败"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.listed,
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="关键审计事项"):
        await svc.update_status(report.id, ReportStatus.final)


@pytest.mark.asyncio
async def test_finalize_listed_with_kam_succeeds(db_session: AsyncSession, seeded_db):
    """上市公司 finalize 时有 KAM 应成功"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.listed,
    )
    await db_session.commit()

    # Add KAM content
    await svc.update_paragraph(
        report.id, "关键审计事项段",
        "关键审计事项一：收入确认\n我们认为收入确认是关键审计事项..."
    )
    await db_session.commit()

    updated = await svc.update_status(report.id, ReportStatus.final)
    assert updated.status == ReportStatus.final


@pytest.mark.asyncio
async def test_finalize_non_listed_without_kam_succeeds(db_session: AsyncSession, seeded_db):
    """非上市公司 finalize 时无 KAM 也应成功"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    updated = await svc.update_status(report.id, ReportStatus.final)
    assert updated.status == ReportStatus.final


@pytest.mark.asyncio
async def test_update_status_draft_to_review(db_session: AsyncSession, seeded_db):
    """状态从 draft 更新到 review"""
    svc = AuditReportService(db_session)
    report = await svc.generate_report(
        FAKE_PROJECT_ID, 2025,
        OpinionType.unqualified, CompanyType.non_listed,
    )
    await db_session.commit()

    updated = await svc.update_status(report.id, ReportStatus.review)
    assert updated.status == ReportStatus.review


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
async def test_api_load_seed_templates(client: AsyncClient):
    """POST /api/audit-report/templates/load-seed"""
    resp = await client.post("/api/audit-report/templates/load-seed")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["loaded_count"] > 0


@pytest.mark.asyncio
async def test_api_get_templates(client: AsyncClient):
    """GET /api/audit-report/templates"""
    resp = await client.get("/api/audit-report/templates")
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert len(items) > 0


@pytest.mark.asyncio
async def test_api_get_templates_filtered(client: AsyncClient):
    """GET /api/audit-report/templates?opinion_type=unqualified&company_type=non_listed"""
    resp = await client.get(
        "/api/audit-report/templates",
        params={"opinion_type": "unqualified", "company_type": "non_listed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("data", data)
    assert len(items) == 7


@pytest.mark.asyncio
async def test_api_generate_report(client: AsyncClient):
    """POST /api/audit-report/generate"""
    resp = await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "unqualified",
            "company_type": "non_listed",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["opinion_type"] == "unqualified"
    assert result["paragraphs"] is not None


@pytest.mark.asyncio
async def test_api_get_report(client: AsyncClient):
    """GET /api/audit-report/{project_id}/{year}"""
    # First generate
    await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "unqualified",
            "company_type": "non_listed",
        },
    )

    resp = await client.get(f"/api/audit-report/{FAKE_PROJECT_ID}/2025")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["opinion_type"] == "unqualified"


@pytest.mark.asyncio
async def test_api_get_report_not_found(client: AsyncClient):
    """GET 不存在的审计报告返回 404"""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/audit-report/{fake_id}/2025")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_update_paragraph(client: AsyncClient):
    """PUT /api/audit-report/{id}/paragraphs/{section}"""
    # Generate first
    gen_resp = await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "unqualified",
            "company_type": "non_listed",
        },
    )
    gen_data = gen_resp.json()
    report_id = gen_data.get("data", gen_data)["id"]

    resp = await client.put(
        f"/api/audit-report/{report_id}/paragraphs/审计意见段",
        json={"section_name": "审计意见段", "content": "自定义内容"},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["paragraphs"]["审计意见段"] == "自定义内容"


@pytest.mark.asyncio
async def test_api_update_status(client: AsyncClient):
    """PUT /api/audit-report/{id}/status"""
    gen_resp = await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "unqualified",
            "company_type": "non_listed",
        },
    )
    gen_data = gen_resp.json()
    report_id = gen_data.get("data", gen_data)["id"]

    resp = await client.put(
        f"/api/audit-report/{report_id}/status",
        json={"status": "review"},
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["status"] == "review"


@pytest.mark.asyncio
async def test_api_finalize_listed_without_kam(client: AsyncClient):
    """PUT /api/audit-report/{id}/status — 上市公司无KAM应返回400"""
    gen_resp = await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "unqualified",
            "company_type": "listed",
        },
    )
    gen_data = gen_resp.json()
    report_id = gen_data.get("data", gen_data)["id"]

    resp = await client.put(
        f"/api/audit-report/{report_id}/status",
        json={"status": "final"},
    )
    assert resp.status_code == 400
