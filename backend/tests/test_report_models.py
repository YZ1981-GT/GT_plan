"""报表模型测试 — 验证8张报表相关表的创建和基本CRUD

Validates: Requirements 9.1-9.8
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.report_models import (
    AuditReport,
    AuditReportTemplate,
    CashFlowCategory,
    CfsAdjustment,
    CompanyType,
    ContentType,
    DisclosureNote,
    ExportTask,
    ExportTaskStatus,
    ExportTaskType,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    NoteValidationResult,
    OpinionType,
    ReportConfig,
    ReportStatus,
    SourceTemplate,
)

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
    """创建基础测试数据：用户和项目"""
    user = User(
        id=FAKE_USER_ID,
        username="test_user",
        email="test@example.com",
        hashed_password="hashed",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=FAKE_PROJECT_ID,
        name="报表测试项目_2025",
        client_name="报表测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== 1. report_config =====


@pytest.mark.asyncio
async def test_report_config_crud(db_session: AsyncSession):
    """report_config 表基本CRUD"""
    rc = ReportConfig(
        report_type=FinancialReportType.balance_sheet,
        row_number=1,
        row_code="BS-001",
        row_name="货币资金",
        indent_level=1,
        formula="TB('1001','期末余额') + TB('1002','期末余额')",
        applicable_standard="enterprise",
        is_total_row=False,
    )
    db_session.add(rc)
    await db_session.commit()

    result = await db_session.execute(
        select(ReportConfig).where(ReportConfig.row_code == "BS-001")
    )
    row = result.scalar_one()
    assert row.report_type == FinancialReportType.balance_sheet
    assert row.row_name == "货币资金"
    assert row.indent_level == 1
    assert row.formula is not None
    assert row.is_total_row is False


@pytest.mark.asyncio
async def test_report_config_total_row(db_session: AsyncSession):
    """report_config 合计行"""
    rc = ReportConfig(
        report_type=FinancialReportType.balance_sheet,
        row_number=99,
        row_code="BS-TOTAL",
        row_name="资产合计",
        indent_level=0,
        formula="ROW('BS-001') + ROW('BS-002')",
        applicable_standard="enterprise",
        is_total_row=True,
    )
    db_session.add(rc)
    await db_session.commit()

    result = await db_session.execute(
        select(ReportConfig).where(ReportConfig.row_code == "BS-TOTAL")
    )
    row = result.scalar_one()
    assert row.is_total_row is True


# ===== 2. financial_report =====


@pytest.mark.asyncio
async def test_financial_report_crud(db_session: AsyncSession, seeded_db):
    """financial_report 表基本CRUD"""
    pid = seeded_db
    fr = FinancialReport(
        project_id=pid,
        year=2025,
        report_type=FinancialReportType.balance_sheet,
        row_code="BS-001",
        row_name="货币资金",
        current_period_amount=Decimal("1500000.00"),
        prior_period_amount=Decimal("1200000.00"),
        formula_used="TB('1001','期末余额')",
        source_accounts=["1001", "1002"],
        generated_at=datetime.now(),
    )
    db_session.add(fr)
    await db_session.commit()

    result = await db_session.execute(
        select(FinancialReport).where(FinancialReport.project_id == pid)
    )
    row = result.scalar_one()
    assert row.current_period_amount == Decimal("1500000.00")
    assert row.prior_period_amount == Decimal("1200000.00")
    assert row.source_accounts == ["1001", "1002"]


# ===== 3. cfs_adjustments =====


@pytest.mark.asyncio
async def test_cfs_adjustment_crud(db_session: AsyncSession, seeded_db):
    """cfs_adjustments 表基本CRUD"""
    pid = seeded_db
    adj = CfsAdjustment(
        project_id=pid,
        year=2025,
        adjustment_no="CFS-001",
        description="折旧调整",
        debit_account="累计折旧",
        credit_account="经营活动现金流",
        amount=Decimal("50000.00"),
        cash_flow_category=CashFlowCategory.operating,
        cash_flow_line_item="固定资产折旧",
        created_by=FAKE_USER_ID,
    )
    db_session.add(adj)
    await db_session.commit()

    result = await db_session.execute(
        select(CfsAdjustment).where(CfsAdjustment.project_id == pid)
    )
    row = result.scalar_one()
    assert row.amount == Decimal("50000.00")
    assert row.cash_flow_category == CashFlowCategory.operating
    assert row.is_auto_generated is False


# ===== 4. disclosure_notes =====


@pytest.mark.asyncio
async def test_disclosure_note_crud(db_session: AsyncSession, seeded_db):
    """disclosure_notes 表基本CRUD"""
    pid = seeded_db
    note = DisclosureNote(
        project_id=pid,
        year=2025,
        note_section="五、1",
        section_title="货币资金",
        account_name="货币资金",
        content_type=ContentType.table,
        table_data={
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {"label": "库存现金", "values": [50000, 45000]},
                {"label": "银行存款", "values": [1400000, 1100000]},
            ],
        },
        source_template=SourceTemplate.soe,
        status=NoteStatus.draft,
        sort_order=1,
    )
    db_session.add(note)
    await db_session.commit()

    result = await db_session.execute(
        select(DisclosureNote).where(DisclosureNote.project_id == pid)
    )
    row = result.scalar_one()
    assert row.note_section == "五、1"
    assert row.content_type == ContentType.table
    assert row.status == NoteStatus.draft
    assert row.table_data["headers"] == ["项目", "期末余额", "期初余额"]


@pytest.mark.asyncio
async def test_disclosure_note_text_type(db_session: AsyncSession, seeded_db):
    """disclosure_notes 文字型附注"""
    pid = seeded_db
    note = DisclosureNote(
        project_id=pid,
        year=2025,
        note_section="一、1",
        section_title="公司概况",
        content_type=ContentType.text,
        text_content="XX有限公司成立于...",
        source_template=SourceTemplate.soe,
        sort_order=0,
    )
    db_session.add(note)
    await db_session.commit()

    result = await db_session.execute(
        select(DisclosureNote).where(DisclosureNote.note_section == "一、1")
    )
    row = result.scalar_one()
    assert row.content_type == ContentType.text
    assert "XX有限公司" in row.text_content


# ===== 5. audit_report =====


@pytest.mark.asyncio
async def test_audit_report_crud(db_session: AsyncSession, seeded_db):
    """audit_report 表基本CRUD"""
    pid = seeded_db
    ar = AuditReport(
        project_id=pid,
        year=2025,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        report_date=date(2025, 3, 31),
        signing_partner="张三",
        paragraphs={"审计意见段": "我们审计了..."},
        financial_data={"total_assets": 10000000},
        status=ReportStatus.draft,
        created_by=FAKE_USER_ID,
    )
    db_session.add(ar)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditReport).where(AuditReport.project_id == pid)
    )
    row = result.scalar_one()
    assert row.opinion_type == OpinionType.unqualified
    assert row.company_type == CompanyType.non_listed
    assert row.signing_partner == "张三"
    assert row.status == ReportStatus.draft


# ===== 6. audit_report_template =====


@pytest.mark.asyncio
async def test_audit_report_template_crud(db_session: AsyncSession):
    """audit_report_template 表基本CRUD"""
    tpl = AuditReportTemplate(
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        section_name="审计意见段",
        section_order=1,
        template_text="我们审计了{entity_name}的财务报表...",
        is_required=True,
    )
    db_session.add(tpl)
    await db_session.commit()

    result = await db_session.execute(
        select(AuditReportTemplate).where(
            AuditReportTemplate.section_name == "审计意见段"
        )
    )
    row = result.scalar_one()
    assert row.opinion_type == OpinionType.unqualified
    assert "{entity_name}" in row.template_text
    assert row.is_required is True


# ===== 7. export_tasks =====


@pytest.mark.asyncio
async def test_export_task_crud(db_session: AsyncSession, seeded_db):
    """export_tasks 表基本CRUD"""
    pid = seeded_db
    task = ExportTask(
        project_id=pid,
        task_type=ExportTaskType.full_archive,
        status=ExportTaskStatus.queued,
        progress_percentage=0,
        password_protected=True,
        created_by=FAKE_USER_ID,
    )
    db_session.add(task)
    await db_session.commit()

    result = await db_session.execute(
        select(ExportTask).where(ExportTask.project_id == pid)
    )
    row = result.scalar_one()
    assert row.task_type == ExportTaskType.full_archive
    assert row.status == ExportTaskStatus.queued
    assert row.password_protected is True
    assert row.progress_percentage == 0


@pytest.mark.asyncio
async def test_export_task_status_update(db_session: AsyncSession, seeded_db):
    """export_tasks 状态更新"""
    pid = seeded_db
    task = ExportTask(
        project_id=pid,
        task_type=ExportTaskType.single_document,
        document_type="audit_report",
        status=ExportTaskStatus.queued,
        created_by=FAKE_USER_ID,
    )
    db_session.add(task)
    await db_session.flush()

    task.status = ExportTaskStatus.completed
    task.progress_percentage = 100
    task.file_path = "/exports/report.pdf"
    task.file_size = 1024000
    task.completed_at = datetime.now()
    await db_session.commit()

    result = await db_session.execute(
        select(ExportTask).where(ExportTask.id == task.id)
    )
    row = result.scalar_one()
    assert row.status == ExportTaskStatus.completed
    assert row.progress_percentage == 100
    assert row.file_size == 1024000


# ===== 8. note_validation_results =====


@pytest.mark.asyncio
async def test_note_validation_result_crud(db_session: AsyncSession, seeded_db):
    """note_validation_results 表基本CRUD"""
    pid = seeded_db
    nvr = NoteValidationResult(
        project_id=pid,
        year=2025,
        validation_timestamp=datetime.now(),
        findings=[
            {
                "note_section": "五、1",
                "check_type": "balance",
                "severity": "error",
                "message": "附注合计与报表不一致",
                "expected_value": 1500000,
                "actual_value": 1400000,
            }
        ],
        error_count=1,
        warning_count=0,
        info_count=0,
        validated_by=FAKE_USER_ID,
    )
    db_session.add(nvr)
    await db_session.commit()

    result = await db_session.execute(
        select(NoteValidationResult).where(NoteValidationResult.project_id == pid)
    )
    row = result.scalar_one()
    assert row.error_count == 1
    assert len(row.findings) == 1
    assert row.findings[0]["check_type"] == "balance"


# ===== 枚举类型测试 =====


@pytest.mark.asyncio
async def test_all_report_types(db_session: AsyncSession):
    """验证四种报表类型枚举"""
    for i, rt in enumerate(FinancialReportType):
        rc = ReportConfig(
            report_type=rt,
            row_number=1,
            row_code=f"TEST-{rt.value}",
            row_name=f"测试行-{rt.value}",
            applicable_standard="enterprise",
        )
        db_session.add(rc)
    await db_session.commit()

    result = await db_session.execute(select(ReportConfig))
    rows = result.scalars().all()
    types = {r.report_type for r in rows}
    assert types == {
        FinancialReportType.balance_sheet,
        FinancialReportType.income_statement,
        FinancialReportType.cash_flow_statement,
        FinancialReportType.equity_statement,
    }


@pytest.mark.asyncio
async def test_all_opinion_types(db_session: AsyncSession):
    """验证四种审计意见类型枚举"""
    for i, ot in enumerate(OpinionType):
        tpl = AuditReportTemplate(
            opinion_type=ot,
            company_type=CompanyType.non_listed,
            section_name=f"测试段落-{ot.value}",
            section_order=i + 1,
            template_text=f"模板文本-{ot.value}",
        )
        db_session.add(tpl)
    await db_session.commit()

    result = await db_session.execute(select(AuditReportTemplate))
    rows = result.scalars().all()
    types = {r.opinion_type for r in rows}
    assert types == {
        OpinionType.unqualified,
        OpinionType.qualified,
        OpinionType.adverse,
        OpinionType.disclaimer,
    }
