"""deliverable-center P1 质量与合规测试"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport, CompanyType, OpinionType, ReportStatus

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
]
from app.services.completeness_service import CompletenessService
from app.services.deliverable_permissions import DeliverableAction, can_deliverable
from app.services.deliverable_service import DeliverableService
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService
from app.services.report_body_service import ReportBodyService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=_DELIVERABLE_TABLES
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    user = User(
        id=user_id,
        username=f"p1_{suffix}",
        email=f"p1_{suffix}@test.com",
        hashed_password="x",
        role=UserRole.manager,
    )
    db_session.add(user)
    project = Project(
        id=project_id,
        name="P1测试项目",
        client_name="P1客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.flush()
    return {"project_id": project_id, "user_id": user_id, "year": 2024}


@pytest.mark.asyncio
async def test_completeness_missing_trio(db_session, seeded_db):
    """Property 18: 三件套齐全性判定 — 缺失时未通过"""
    result = await CompletenessService(db_session).check(
        seeded_db["project_id"], seeded_db["year"]
    )
    assert result.passed is False
    assert len(result.missing_doc_types) >= 1


@pytest.mark.asyncio
async def test_completeness_passed_with_confirmed(db_session, seeded_db):
    """Property 19: 完整性通过判定"""
    tb = "same_tb_hash"
    for doc_type in ("audit_report", "financial_report", "disclosure_notes"):
        svc = DeliverableService(db_session)
        task = await svc.create_task(
            seeded_db["project_id"], doc_type, "soe", seeded_db["user_id"]
        )
        task.source_snapshot_refs = {"tb_hash": tb, "year": seeded_db["year"]}
        task.file_path = f"/tmp/{doc_type}.docx"
        task.status = WordExportStatus.confirmed.value
        if doc_type == "financial_report":
            task.selected_sections = ["balance_sheet", "income_statement"]
        await db_session.flush()

    result = await CompletenessService(db_session).check(
        seeded_db["project_id"], seeded_db["year"]
    )
    assert result.passed is True
    assert result.has_confirmed is True
    assert result.trio_consistent is True


@pytest.mark.asyncio
async def test_eqcr_gate_blocks_confirm(db_session, seeded_db):
    """Property 29: EQCR 守卫 — 未通过 EQCR 时阻止 confirmed"""
    svc = DeliverableService(db_session)
    task = await svc.create_task(
        seeded_db["project_id"], "audit_report", "soe", seeded_db["user_id"]
    )
    await svc.update_status(task.id, WordExportStatus.generating.value)
    await svc.update_status(task.id, WordExportStatus.generated.value)
    await svc.update_status(task.id, WordExportStatus.editing.value)

    with pytest.raises(ValueError, match="EQCR"):
        await svc.confirm_deliverable(task.id, seeded_db["user_id"], seeded_db["year"])


@pytest.mark.asyncio
async def test_eqcr_gate_allows_confirm(db_session, seeded_db):
    """Property 29: EQCR 通过后允许 confirmed"""
    report = AuditReport(
        project_id=seeded_db["project_id"],
        year=seeded_db["year"],
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.eqcr_approved,
        created_by=seeded_db["user_id"],
    )
    db_session.add(report)
    await db_session.flush()

    svc = DeliverableService(db_session)
    task = await svc.create_task(
        seeded_db["project_id"], "audit_report", "soe", seeded_db["user_id"]
    )
    await svc.update_status(task.id, WordExportStatus.generating.value)
    await svc.update_status(task.id, WordExportStatus.generated.value)
    await svc.update_status(task.id, WordExportStatus.editing.value)

    confirmed = await svc.confirm_deliverable(
        task.id, seeded_db["user_id"], seeded_db["year"]
    )
    assert confirmed.status == WordExportStatus.confirmed.value


@pytest.mark.asyncio
async def test_sign_records_fields(db_session, seeded_db):
    """Property 30: 签章字段完整性"""
    report = AuditReport(
        project_id=seeded_db["project_id"],
        year=seeded_db["year"],
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.eqcr_approved,
        created_by=seeded_db["user_id"],
    )
    db_session.add(report)
    await db_session.flush()

    svc = DeliverableService(db_session)
    task = await svc.create_task(
        seeded_db["project_id"], "audit_report", "soe", seeded_db["user_id"]
    )
    await svc.update_status(task.id, WordExportStatus.generating.value)
    await svc.update_status(task.id, WordExportStatus.generated.value)
    await svc.update_status(task.id, WordExportStatus.editing.value)
    await svc.confirm_deliverable(task.id, seeded_db["user_id"], seeded_db["year"])

    signed = await svc.sign(
        task.id, seeded_db["user_id"], "项目合伙人", seeded_db["year"]
    )
    assert signed.status == WordExportStatus.signed.value
    assert signed.signed_by == seeded_db["user_id"]
    assert signed.signed_at is not None
    assert signed.sign_type == "项目合伙人"


@given(
    role=st.sampled_from(["readonly", "auditor", "manager", "partner", "admin"]),
    is_eqcr=st.booleans(),
)
@settings(max_examples=5)
def test_permission_matrix_export(role, is_eqcr):
    """Property 34: 权限矩阵 — 导出/只读/EQCR"""
    allowed_export = can_deliverable(
        role, DeliverableAction.export, is_eqcr_assignment=is_eqcr
    )
    if is_eqcr:
        assert allowed_export is False
    elif role in ("auditor", "manager", "partner", "admin"):
        assert allowed_export is True
    else:
        assert allowed_export is False


@given(
    role=st.sampled_from(["auditor", "manager", "partner", "admin"]),
    status=st.sampled_from(["editing", "confirmed", "signed", "archived"]),
)
@settings(max_examples=5)
def test_permission_matrix_edit(role, status):
    """Property 34: 权限矩阵 — 编辑锁定态"""
    allowed = can_deliverable(
        role, DeliverableAction.edit, task_status=status, is_eqcr_assignment=False
    )
    if status in ("confirmed", "signed", "archived"):
        assert allowed is False
    else:
        assert allowed is True


@pytest.mark.asyncio
async def test_report_date_compliance_warning(db_session, seeded_db):
    """Property 51: 报告日期下界合规 — 早于下界时告警"""
    project = await db_session.get(Project, seeded_db["project_id"])
    project.wizard_state = {
        "steps": {
            "basic_info": {
                "data": {"fs_approval_date": "2024-06-30"},
            }
        }
    }
    await db_session.flush()

    rbs = ReportBodyService(db_session)
    result = await rbs.check_report_date_compliance(
        seeded_db["project_id"], seeded_db["year"], date(2024, 3, 1)
    )
    assert result["compliant"] is False
    assert result["warnings"]


# Feature: audit-report-deliverable-center, Property 51: 报告日期下界合规
@given(
    base_year=st.integers(min_value=2020, max_value=2030),
    offsets=st.lists(
        st.integers(min_value=-400, max_value=400), min_size=0, max_size=3
    ),
    report_offset=st.integers(min_value=-400, max_value=400),
    which=st.lists(st.sampled_from([0, 1, 2]), min_size=0, max_size=3, unique=True),
)
@settings(max_examples=5, deadline=None)
def test_property_51_report_date_lower_bound_compliance(
    base_year, offsets, report_offset, which
):
    """Property 51: 报告日期下界合规 —

    对任意提供的下界日期子集（审计证据完成日 / 财表批准日 / EQCR 通过日），
    校验当且仅当 report_date < max(已提供下界) 时返回告警并要求确认（非硬阻断）。
    Validates: Requirements 25.1, 25.2, 25.3
    """
    anchor = date(base_year, 6, 30)

    def _shift(d: date, days: int) -> date:
        from datetime import timedelta

        return d + timedelta(days=days)

    # 三类下界日期：按 which 决定哪些被提供（其余为 None）
    slots: list[date | None] = [None, None, None]
    for idx in which:
        off = offsets[idx % len(offsets)] if offsets else 0
        slots[idx] = _shift(anchor, off)

    report_date = _shift(anchor, report_offset)

    result = ReportBodyService.validate_report_date_compliance(
        report_date,
        evidence_complete_date=slots[0],
        fs_approval_date=slots[1],
        eqcr_pass_date=slots[2],
    )

    provided = [d for d in slots if d is not None]
    if not provided:
        # 无任何下界 → 视为合规
        assert result["compliant"] is True
        assert result["requires_confirmation"] is False
        assert result["warnings"] == []
        assert result["floor_date"] is None
        return

    floor = max(provided)
    expect_warning = report_date < floor

    # 告警 ⟺ report_date < 下界
    assert (result["compliant"] is False) is expect_warning
    assert result["requires_confirmation"] is expect_warning
    assert bool(result["warnings"]) is expect_warning
    # 下界日期始终为已提供日期的最大值
    assert result["floor_date"] == floor.isoformat()
    # 非硬阻断：不合规时通过 requires_confirmation 表达"要求确认"语义
    if expect_warning:
        assert result["requires_confirmation"] is True


def test_property_51_no_floor_dates_is_compliant():
    """Property 51 边界：无任何下界日期输入时恒合规、无需确认。"""
    result = ReportBodyService.validate_report_date_compliance(date(2025, 3, 31))
    assert result["compliant"] is True
    assert result["requires_confirmation"] is False
    assert result["floor_date"] is None


def test_property_51_report_date_equals_floor_is_compliant():
    """Property 51 边界：报告日期恰等于下界时合规（不早于即可）。"""
    floor = date(2025, 4, 15)
    result = ReportBodyService.validate_report_date_compliance(
        floor,
        evidence_complete_date=date(2025, 3, 1),
        fs_approval_date=floor,
        eqcr_pass_date=date(2025, 4, 1),
    )
    assert result["compliant"] is True
    assert result["requires_confirmation"] is False
    assert result["floor_date"] == floor.isoformat()


def test_onlyoffice_disabled_without_secret(monkeypatch):
    """Property 54: OnlyOffice 不可用降级 — 无密钥时禁用"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ONLYOFFICE_JWT_SECRET", "")
    svc = OnlyOfficeCallbackService(db=None)  # type: ignore[arg-type]
    assert svc.enabled is False
    assert svc.verify_callback_jwt(None, {}) is False


def test_onlyoffice_jwt_rejects_invalid(monkeypatch):
    """Property 55: callback JWT 鉴权 — 无效 token 拒绝"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ONLYOFFICE_JWT_SECRET", "test-secret-key")
    svc = OnlyOfficeCallbackService(db=None)  # type: ignore[arg-type]
    assert svc.verify_callback_jwt("not-a-jwt", {"status": 2}) is False
