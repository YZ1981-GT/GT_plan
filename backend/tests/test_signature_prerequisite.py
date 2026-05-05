"""R1 需求 4 — 签字前置依赖校验 + 工作流端点 + 状态机联动

Validates: Round 1 Requirement 4 (Signature prerequisite check, workflow endpoint,
AuditReport status transition)
对应 tasks.md Sprint 1 Task 11。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.extension_models import SignatureRecord
from app.models.report_models import AuditReport, OpinionType, ReportStatus
from app.routers.signatures import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_partner"
        self.email = "partner@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


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
async def client(db_session: AsyncSession):
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_project(db: AsyncSession) -> uuid.UUID:
    project = Project(
        id=uuid.uuid4(),
        name="签字测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db.add(project)
    await db.flush()
    return project.id


async def _make_audit_report(
    db: AsyncSession, project_id: uuid.UUID, status: ReportStatus = ReportStatus.review
) -> uuid.UUID:
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2025,
        opinion_type=OpinionType.unqualified,
        status=status,
        created_by=TEST_USER.id,
    )
    db.add(report)
    await db.flush()
    return report.id


async def _make_signature_record(
    db: AsyncSession,
    report_id: uuid.UUID,
    signer_id: uuid.UUID,
    required_order: int,
    required_role: str,
    signed: bool = False,
    prerequisite_ids: list[str] | None = None,
) -> uuid.UUID:
    """创建签字记录（可选已签/未签）"""
    record = SignatureRecord(
        id=uuid.uuid4(),
        object_type="audit_report",
        object_id=report_id,
        signer_id=signer_id,
        signature_level="level1",
        required_order=required_order,
        required_role=required_role,
        prerequisite_signature_ids=prerequisite_ids,
        signature_timestamp=datetime.utcnow() if signed else datetime.utcnow(),
        ip_address="127.0.0.1",
    )
    db.add(record)
    await db.flush()
    return record.id


# ============================================================================
# 测试：前置依赖校验
# ============================================================================


@pytest.mark.asyncio
async def test_sign_order1_no_prerequisite_success(client, db_session):
    """order=1 签字成功（无前置依赖）"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id)
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 1,
                "required_role": "auditor",
                "prerequisite_signature_ids": None,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["object_type"] == "audit_report"
    assert data["signer_id"] == str(TEST_USER.id)


@pytest.mark.asyncio
async def test_sign_order2_with_prerequisite_signed_success(client, db_session):
    """order=2 签字成功（order=1 已签）"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id)

    # 创建 order=1 已签记录
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 2,
                "required_role": "manager",
                "prerequisite_signature_ids": [str(sig1_id)],
            },
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sign_order2_prerequisite_not_met_403(client, db_session):
    """order=2 签字但 order=1 未签 → 403 PREREQUISITE_NOT_MET"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id)
    await db_session.commit()

    # 使用一个不存在的前置 ID
    fake_prereq_id = str(uuid.uuid4())

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 2,
                "required_role": "manager",
                "prerequisite_signature_ids": [fake_prereq_id],
            },
        )

    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["error_code"] == "PREREQUISITE_NOT_MET"
    assert fake_prereq_id in data["detail"]["missing_ids"]


# ============================================================================
# 测试：工作流端点
# ============================================================================


@pytest.mark.asyncio
async def test_workflow_endpoint_returns_correct_status(client, db_session):
    """GET /api/signatures/workflow/{project_id} 返回正确 status 列表"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id)

    # order=1 已签
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    # order=2 未签，前置是 sig1
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    # order=3 未签，前置是 sig2（但 sig2 已签所以 ready）
    await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 3, "partner", signed=True,
        prerequisite_ids=[str(sig2_id)]
    )
    await db_session.commit()

    resp = await client.get(f"/api/signatures/workflow/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["order"] == 1
    assert data[0]["status"] == "signed"
    assert data[1]["order"] == 2
    assert data[1]["status"] == "signed"
    assert data[2]["order"] == 3
    assert data[2]["status"] == "signed"


@pytest.mark.asyncio
async def test_workflow_endpoint_waiting_status(client, db_session):
    """工作流端点：前置未签时 status=waiting"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id)

    # order=1 已签
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    # order=2 已签
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    # order=3 未签，前置是一个不存在的 ID（模拟前置未签）
    # 需要创建一个没有 signature_timestamp 的记录
    unsig_record = SignatureRecord(
        id=uuid.uuid4(),
        object_type="audit_report",
        object_id=report_id,
        signer_id=uuid.uuid4(),
        signature_level="level1",
        required_order=3,
        required_role="partner",
        prerequisite_signature_ids=[str(uuid.uuid4())],  # 不存在的前置
        signature_timestamp=None,
        ip_address=None,
    )
    db_session.add(unsig_record)
    await db_session.flush()
    await db_session.commit()

    resp = await client.get(f"/api/signatures/workflow/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # order=3 的前置 ID 不存在于已签集合中，所以 status=waiting
    assert data[2]["status"] == "waiting"


@pytest.mark.asyncio
async def test_workflow_endpoint_empty_project(client, db_session):
    """工作流端点：无签字记录返回空列表"""
    project_id = await _make_project(db_session)
    await db_session.commit()

    resp = await client.get(f"/api/signatures/workflow/{project_id}")
    assert resp.status_code == 200
    assert resp.json() == []


# ============================================================================
# 测试：最高级签字后 AuditReport.status 切 final
# ============================================================================


@pytest.mark.asyncio
async def test_highest_order_sign_transitions_to_final(client, db_session):
    """无 EQCR：order=3（最高级）签完后 AuditReport.status 从 review → final"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id, ReportStatus.review)

    # 先创建 order=1, order=2 已签记录
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 3,
                "required_role": "partner",
                "prerequisite_signature_ids": [str(sig2_id)],
            },
        )

    assert resp.status_code == 200

    # 验证 AuditReport.status 已切到 final
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(AuditReport).where(AuditReport.id == report_id)
    )
    report = result.scalar_one()
    assert report.status == ReportStatus.final


@pytest.mark.asyncio
async def test_status_transition_fails_rollback(client, db_session):
    """切态失败（status 不是 review）→ 签字动作整体回滚"""
    project_id = await _make_project(db_session)
    # 报告状态是 draft 而非 review，切态应失败
    report_id = await _make_audit_report(db_session, project_id, ReportStatus.draft)

    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 3,
                "required_role": "partner",
                "prerequisite_signature_ids": [str(sig2_id)],
            },
        )

    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["error_code"] == "STATUS_TRANSITION_FAILED"


@pytest.mark.asyncio
async def test_eqcr_order4_transitions_to_eqcr_approved(client, db_session):
    """有 EQCR：order=4 签完后 AuditReport.status 从 review → eqcr_approved"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(db_session, project_id, ReportStatus.review)

    # 创建 order=1~3 已签 + order=5 占位（表示 max_order=5，有 EQCR）
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    sig3_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 3, "partner", signed=True,
        prerequisite_ids=[str(sig2_id)]
    )
    # order=5 占位（未签）- 表示这是 EQCR 项目
    sig5_record = SignatureRecord(
        id=uuid.uuid4(),
        object_type="audit_report",
        object_id=report_id,
        signer_id=uuid.uuid4(),
        signature_level="level1",
        required_order=5,
        required_role="archive_signer",
        prerequisite_signature_ids=None,
        signature_timestamp=datetime.utcnow(),
        ip_address="127.0.0.1",
    )
    db_session.add(sig5_record)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 4,
                "required_role": "eqcr",
                "prerequisite_signature_ids": [str(sig3_id)],
            },
        )

    assert resp.status_code == 200

    # 验证 AuditReport.status 已切到 eqcr_approved
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(AuditReport).where(AuditReport.id == report_id)
    )
    report = result.scalar_one()
    assert report.status == ReportStatus.eqcr_approved


@pytest.mark.asyncio
async def test_eqcr_order5_transitions_to_final(client, db_session):
    """有 EQCR：order=5 签完后 AuditReport.status 从 eqcr_approved → final"""
    project_id = await _make_project(db_session)
    report_id = await _make_audit_report(
        db_session, project_id, ReportStatus.eqcr_approved
    )

    # 创建 order=1~4 已签
    sig1_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 1, "auditor", signed=True
    )
    sig2_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 2, "manager", signed=True,
        prerequisite_ids=[str(sig1_id)]
    )
    sig3_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 3, "partner", signed=True,
        prerequisite_ids=[str(sig2_id)]
    )
    sig4_id = await _make_signature_record(
        db_session, report_id, uuid.uuid4(), 4, "eqcr", signed=True,
        prerequisite_ids=[str(sig3_id)]
    )
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/signatures/sign",
            json={
                "object_type": "audit_report",
                "object_id": str(report_id),
                "signer_id": str(TEST_USER.id),
                "signature_level": "level1",
                "required_order": 5,
                "required_role": "archive_signer",
                "prerequisite_signature_ids": [str(sig4_id)],
            },
        )

    assert resp.status_code == 200

    # 验证 AuditReport.status 已切到 final
    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(AuditReport).where(AuditReport.id == report_id)
    )
    report = result.scalar_one()
    assert report.status == ReportStatus.final
