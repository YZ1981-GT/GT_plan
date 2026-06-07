"""deliverable-center 签章与 EQCR 守卫 属性化测试

Property 29: EQCR 守卫
Property 30: 签章字段完整性

后端 PBT 用 Hypothesis，max_examples=5（项目铁律）。
为每个 hypothesis 样例建独立内存库（asyncio.run），避免跨样例状态污染。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import (
    AuditReport,
    CompanyType,
    OpinionType,
    ReportStatus,
)
from app.services.deliverable_service import DeliverableService

# Feature: audit-report-deliverable-center

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
    AuditLogEntry.__table__,
]

# EQCR「已通过」状态集合（与 DeliverableService._assert_eqcr_passed 对齐）
_EQCR_PASSED_STATUSES = (ReportStatus.eqcr_approved, ReportStatus.final)
# EQCR「未通过」状态集合
_EQCR_NOT_PASSED_STATUSES = (ReportStatus.draft, ReportStatus.review)
_ALL_REPORT_STATUSES = _EQCR_PASSED_STATUSES + _EQCR_NOT_PASSED_STATUSES


async def _seed_project_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"sign_{suffix}",
            email=f"sign_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.partner,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="签章测试项目",
            client_name="签章测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory):
    """为单个 hypothesis 样例建独立内存库并运行 coro_factory(session, project_id, user_id)。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session)
                await session.commit()
                return await coro_factory(session, project_id, user_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


async def _set_eqcr(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    status: ReportStatus,
) -> None:
    session.add(
        AuditReport(
            project_id=project_id,
            year=year,
            opinion_type=OpinionType.unqualified,
            company_type=CompanyType.non_listed,
            status=status,
            created_by=user_id,
        )
    )
    await session.flush()


async def _advance_to_editing(svc: DeliverableService, task_id: uuid.UUID) -> None:
    await svc.update_status(task_id, WordExportStatus.generating.value)
    await svc.update_status(task_id, WordExportStatus.generated.value)
    await svc.update_status(task_id, WordExportStatus.editing.value)


# ---------------------------------------------------------------------------
# Property 29: EQCR 守卫
# Feature: audit-report-deliverable-center, Property 29: EQCR 守卫
# ---------------------------------------------------------------------------
# For any 交付物，转入 confirmed 被允许 当且仅当 项目 EQCR 复核已通过；未通过则阻止。
# Validates: Requirements 14.1, 14.2


@given(
    report_status=st.sampled_from(_ALL_REPORT_STATUSES),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_eqcr_guard_confirm_iff_passed(report_status, year):
    # Feature: audit-report-deliverable-center, Property 29: EQCR 守卫
    """Property 29: confirm 成功 当且仅当 EQCR 状态 ∈ {eqcr_approved, final}。"""

    async def _scenario(session, project_id, user_id):
        await _set_eqcr(session, project_id, user_id, year, report_status)
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        await _advance_to_editing(svc, task.id)

        eqcr_passed = report_status in _EQCR_PASSED_STATUSES
        if eqcr_passed:
            confirmed = await svc.confirm_deliverable(task.id, user_id, year)
            assert confirmed.status == WordExportStatus.confirmed.value
        else:
            with pytest.raises(ValueError, match="EQCR"):
                await svc.confirm_deliverable(task.id, user_id, year)
            # 阻止后状态不应变为 confirmed
            still = await svc.get_task(task.id)
            assert still.status == WordExportStatus.editing.value

    _run_in_isolated_db(_scenario)


@given(year=st.integers(min_value=2018, max_value=2030))
@settings(max_examples=5, deadline=None)
def test_eqcr_guard_blocks_when_no_report(year):
    # Feature: audit-report-deliverable-center, Property 29: EQCR 守卫
    """Property 29 边界：项目无 AuditReport（EQCR 未发起）时 confirm 被阻止。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        await _advance_to_editing(svc, task.id)
        with pytest.raises(ValueError, match="EQCR"):
            await svc.confirm_deliverable(task.id, user_id, year)

    _run_in_isolated_db(_scenario)


# ---------------------------------------------------------------------------
# Property 30: 签章字段完整性
# Feature: audit-report-deliverable-center, Property 30: 签章字段完整性
# ---------------------------------------------------------------------------
# For any 转入 signed 的交付物，signed_by / signed_at / sign_type 三字段均非空。
# Validates: Requirements 14.3


@given(
    sign_type=st.sampled_from(["项目合伙人", "复核合伙人", "project_partner", "eqcr_partner"]),
    eqcr_status=st.sampled_from(_EQCR_PASSED_STATUSES),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_sign_fields_complete(sign_type, eqcr_status, year):
    # Feature: audit-report-deliverable-center, Property 30: 签章字段完整性
    """Property 30: 签章后 signed_by/signed_at/sign_type 全部非空且 sign_type 被忠实记录。"""

    async def _scenario(session, project_id, user_id):
        await _set_eqcr(session, project_id, user_id, year, eqcr_status)
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        await _advance_to_editing(svc, task.id)
        await svc.confirm_deliverable(task.id, user_id, year)

        signed = await svc.sign(task.id, user_id, sign_type, year)
        assert signed.status == WordExportStatus.signed.value
        assert signed.signed_by == user_id
        assert signed.signed_at is not None
        assert signed.sign_type == sign_type

    _run_in_isolated_db(_scenario)


@given(
    bad_status=st.sampled_from(
        [
            WordExportStatus.draft,
            WordExportStatus.generated,
            WordExportStatus.editing,
        ]
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_sign_requires_confirmed(bad_status, year):
    # Feature: audit-report-deliverable-center, Property 30: 签章字段完整性
    """Property 30 边界：非 confirmed 态签章被拒，签章字段保持为空。"""

    async def _scenario(session, project_id, user_id):
        await _set_eqcr(session, project_id, user_id, year, ReportStatus.eqcr_approved)
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        # 仅推进到 bad_status（不到 confirmed）
        if bad_status != WordExportStatus.draft:
            await svc.update_status(task.id, WordExportStatus.generating.value)
            await svc.update_status(task.id, WordExportStatus.generated.value)
        if bad_status == WordExportStatus.editing:
            await svc.update_status(task.id, WordExportStatus.editing.value)

        with pytest.raises(ValueError):
            await svc.sign(task.id, user_id, "项目合伙人", year)

        unsigned = await svc.get_task(task.id)
        assert unsigned.signed_by is None
        assert unsigned.signed_at is None
        assert unsigned.sign_type is None

    _run_in_isolated_db(_scenario)
