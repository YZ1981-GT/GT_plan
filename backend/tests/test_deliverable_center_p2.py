"""deliverable-center P2 增强测试"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobItem,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport, CompanyType, OpinionType, ReportStatus
from app.services.deliverable_hash_service import DeliverableHashService, compute_file_sha256
from app.services.deliverable_permissions import DeliverableAction, can_deliverable
from app.services.deliverable_service import DeliverableService
from app.services.report_body_service import ReportBodyService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
    AuditLogEntry.__table__,
    ExportJob.__table__,
    ExportJobItem.__table__,
]

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
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
        username=f"p2_{suffix}",
        email=f"p2_{suffix}@test.com",
        hashed_password="x",
        role=UserRole.manager,
    )
    db_session.add(user)
    project = Project(
        id=project_id,
        name="P2测试项目",
        client_name="P2客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.reporting,
        created_by=user_id,
    )
    db_session.add(project)
    await db_session.flush()
    return {"project_id": project_id, "user_id": user_id, "year": 2024}


async def _editing_task(db, seeded) -> WordExportTask:
    svc = DeliverableService(db)
    task = await svc.create_task(
        seeded["project_id"], "audit_report", "soe", seeded["user_id"]
    )
    await svc.update_status(task.id, WordExportStatus.generating.value)
    await svc.update_status(task.id, WordExportStatus.generated.value)
    await svc.update_status(task.id, WordExportStatus.editing.value)
    return task


@pytest.mark.asyncio
async def test_approval_flow(db_session, seeded_db):
    """审批流：editing → pending_approval → confirmed"""
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
    task = await _editing_task(db_session, seeded_db)
    submitted = await svc.submit_for_approval(task.id, seeded_db["user_id"])
    assert submitted.status == WordExportStatus.pending_approval.value

    approved = await svc.approve(task.id, seeded_db["user_id"], seeded_db["year"])
    assert approved.status == WordExportStatus.confirmed.value
    assert approved.approval_by == seeded_db["user_id"]


@pytest.mark.asyncio
async def test_reject_leaves_reason(db_session, seeded_db):
    svc = DeliverableService(db_session)
    task = await _editing_task(db_session, seeded_db)
    await svc.submit_for_approval(task.id, seeded_db["user_id"])
    rejected = await svc.reject(task.id, seeded_db["user_id"], "格式不合规")
    assert rejected.status == WordExportStatus.editing.value
    assert rejected.reject_reason == "格式不合规"


@pytest.mark.asyncio
async def test_submit_approval_requires_editing(db_session, seeded_db):
    """需求 7.1：仅 editing 可提交审批，非 editing 应拒绝"""
    svc = DeliverableService(db_session)
    task = await svc.create_task(
        seeded_db["project_id"], "audit_report", "soe", seeded_db["user_id"]
    )
    # 当前为 draft，非 editing
    with pytest.raises(ValueError, match="editing"):
        await svc.submit_for_approval(task.id, seeded_db["user_id"])


@pytest.mark.asyncio
async def test_approve_requires_pending_approval(db_session, seeded_db):
    """需求 7.2：仅 pending_approval 可批准"""
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
    task = await _editing_task(db_session, seeded_db)
    # editing 状态尚未提交审批，直接批准应拒绝
    with pytest.raises(ValueError, match="pending_approval"):
        await svc.approve(task.id, seeded_db["user_id"], seeded_db["year"])


@pytest.mark.asyncio
async def test_reject_requires_pending_approval(db_session, seeded_db):
    """需求 7.3：仅 pending_approval 可驳回"""
    svc = DeliverableService(db_session)
    task = await _editing_task(db_session, seeded_db)
    # editing 状态直接驳回应拒绝
    with pytest.raises(ValueError, match="pending_approval"):
        await svc.reject(task.id, seeded_db["user_id"], "原因")


@pytest.mark.asyncio
async def test_reject_then_resubmit_clears_reject_on_approve(db_session, seeded_db):
    """需求 7.2/7.3：驳回留痕后可重新提交并批准，approve 清除驳回原因"""
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
    task = await _editing_task(db_session, seeded_db)
    await svc.submit_for_approval(task.id, seeded_db["user_id"])
    rejected = await svc.reject(task.id, seeded_db["user_id"], "需修改")
    assert rejected.status == WordExportStatus.editing.value
    assert rejected.reject_reason == "需修改"
    assert rejected.approval_by == seeded_db["user_id"]
    assert rejected.approval_at is not None

    # 重新提交并批准
    await svc.submit_for_approval(task.id, seeded_db["user_id"])
    approved = await svc.approve(task.id, seeded_db["user_id"], seeded_db["year"])
    assert approved.status == WordExportStatus.confirmed.value
    assert approved.reject_reason is None
    assert approved.approval_by == seeded_db["user_id"]
    assert approved.approval_at is not None


@pytest.mark.asyncio
async def test_archive_blocked_without_completeness(db_session, seeded_db):
    svc = DeliverableService(db_session)
    with pytest.raises(ValueError, match="完整性"):
        await svc.archive_project_deliverables(
            seeded_db["project_id"], seeded_db["user_id"], seeded_db["year"]
        )


@pytest.mark.asyncio
async def test_archive_cascades(db_session, seeded_db, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    svc = DeliverableService(db_session)
    task = await _editing_task(db_session, seeded_db)
    await svc.update_status(task.id, WordExportStatus.confirmed.value)

    count = await svc.archive_project_deliverables(
        seeded_db["project_id"],
        seeded_db["user_id"],
        seeded_db["year"],
        force=True,
    )
    assert count == 1
    refreshed = await svc.get_task(task.id)
    assert refreshed.status == WordExportStatus.archived.value


@pytest.mark.asyncio
async def test_hash_chain_and_tamper_detect(db_session, seeded_db, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    svc = DeliverableService(db_session)
    task = await _editing_task(db_session, seeded_db)

    f = tmp_path / "deliverables" / str(task.project_id) / str(task.id)
    f.mkdir(parents=True)
    doc = f / "test.docx"
    doc.write_bytes(b"original content")

    version = await svc.create_version(
        task.id,
        file_path=str(doc),
        html_path=None,
        user_id=seeded_db["user_id"],
    )
    await DeliverableHashService(db_session).bind_version_hash(
        version, task, seeded_db["user_id"]
    )
    await db_session.flush()

    result = await DeliverableHashService(db_session).verify_task_integrity(task.id)
    assert result.valid is True

    doc.write_bytes(b"tampered content")
    result2 = await DeliverableHashService(db_session).verify_task_integrity(task.id)
    assert result2.valid is False
    assert version.version_no in result2.tampered_versions


def test_editor_mode_by_status():
    """Property 16: confirmed/signed/archived 只读"""
    assert can_deliverable("manager", DeliverableAction.edit, task_status="confirmed") is False
    assert can_deliverable("manager", DeliverableAction.edit, task_status="editing") is True


def test_prior_period_other_matter():
    """Property 52: 首次委托注入其他事项段"""
    rbs = ReportBodyService(db=None)  # type: ignore[arg-type]
    body = {"sections": [{"section_id": "opinion", "section_name": "审计意见段"}]}
    out = rbs.apply_prior_period_section(body, "predecessor_auditor")
    names = [s.get("section_name") for s in out["sections"]]
    assert "其他事项段" in names


def test_compute_file_hash(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert compute_file_sha256(p) == compute_file_sha256(p)
