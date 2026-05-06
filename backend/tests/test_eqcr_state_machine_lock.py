"""Task 13: 状态机锁定联动测试

验证：
1. eqcr_approved 态下禁止修改 opinion_type 和段落 → 403 OPINION_LOCKED_BY_EQCR
2. SignService.sign order=4 EQCR 签字完后切状态 review → eqcr_approved
3. SignService.sign order=5 归档签字完后切状态 eqcr_approved → final
4. final 态下所有人都不能改（原有逻辑保持）

Validates: R5 Requirements 5, 6
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# Register all models so SQLite creates all tables
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401

from app.models.core import Project, ProjectStatus, ProjectType
from app.models.extension_models import SignatureRecord
from app.models.report_models import (
    AuditReport,
    CompanyType,
    OpinionType,
    ReportStatus,
)
from app.services.sign_service import SignService

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


async def _create_project(db: AsyncSession) -> Project:
    project = Project(
        id=FAKE_PROJECT_ID,
        name="状态机锁定测试_2025",
        client_name="状态机锁定测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db.add(project)
    await db.flush()
    return project


async def _create_report(
    db: AsyncSession, status: ReportStatus = ReportStatus.draft
) -> AuditReport:
    report = AuditReport(
        project_id=FAKE_PROJECT_ID,
        year=2025,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        paragraphs={"审计意见段": "原始内容", "管理层责任段": "管理层责任"},
        status=status,
        is_deleted=False,
        created_by=FAKE_USER_ID,
    )
    db.add(report)
    await db.flush()
    return report


# -----------------------------------------------------------------------
# SignService 状态机联动测试
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sign_order4_transitions_review_to_eqcr_approved(db_session: AsyncSession):
    """order=4 EQCR 签字完成后，审计报告从 review → eqcr_approved"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.review)

    svc = SignService()
    result = await svc.sign_document(
        db_session,
        object_type="audit_report",
        object_id=report.id,
        signer_id=FAKE_USER_ID,
        level="level1",
        required_order=4,
        required_role="eqcr",
    )

    assert result["required_order"] == 4
    assert result["required_role"] == "eqcr"

    # 刷新对象以获取最新状态
    await db_session.refresh(report)
    assert report.status == ReportStatus.eqcr_approved


@pytest.mark.asyncio
async def test_sign_order5_transitions_eqcr_approved_to_final(db_session: AsyncSession):
    """order=5 归档签字完成后，审计报告从 eqcr_approved → final"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.eqcr_approved)

    svc = SignService()
    result = await svc.sign_document(
        db_session,
        object_type="audit_report",
        object_id=report.id,
        signer_id=FAKE_USER_ID,
        level="level1",
        required_order=5,
        required_role="archive",
    )

    assert result["required_order"] == 5

    # 验证报告状态已切换
    await db_session.refresh(report)
    assert report.status == ReportStatus.final


@pytest.mark.asyncio
async def test_sign_order4_no_transition_if_not_review(db_session: AsyncSession):
    """order=4 签字但报告不在 review 态时，不切换状态"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.draft)

    svc = SignService()
    await svc.sign_document(
        db_session,
        object_type="audit_report",
        object_id=report.id,
        signer_id=FAKE_USER_ID,
        level="level1",
        required_order=4,
        required_role="eqcr",
    )

    # 状态不变
    await db_session.refresh(report)
    assert report.status == ReportStatus.draft


@pytest.mark.asyncio
async def test_sign_order5_no_transition_if_not_eqcr_approved(db_session: AsyncSession):
    """order=5 签字但报告不在 eqcr_approved 态时，不切换状态"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.review)

    svc = SignService()
    await svc.sign_document(
        db_session,
        object_type="audit_report",
        object_id=report.id,
        signer_id=FAKE_USER_ID,
        level="level1",
        required_order=5,
        required_role="archive",
    )

    # 状态不变
    await db_session.refresh(report)
    assert report.status == ReportStatus.review


@pytest.mark.asyncio
async def test_sign_non_audit_report_no_transition(db_session: AsyncSession):
    """非 audit_report 类型的签字不触发状态联动"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.review)

    svc = SignService()
    # 签字对象是 working_paper，不是 audit_report
    await svc.sign_document(
        db_session,
        object_type="working_paper",
        object_id=report.id,
        signer_id=FAKE_USER_ID,
        level="level1",
        required_order=4,
        required_role="eqcr",
    )

    # 报告状态不变
    await db_session.refresh(report)
    assert report.status == ReportStatus.review


# -----------------------------------------------------------------------
# 段落锁定测试（service 层）
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_paragraph_blocked_in_eqcr_approved(db_session: AsyncSession):
    """eqcr_approved 态下 update_paragraph 应被路由层拦截（service 层不做拦截）"""
    from app.services.audit_report_service import AuditReportService

    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.eqcr_approved)

    # Service 层本身不做状态检查（由路由层负责），验证 service 仍可执行
    # 但在实际 API 调用中会被路由层拦截
    svc = AuditReportService(db_session)
    result = await svc.update_paragraph(report.id, "审计意见段", "新内容")
    # Service 层不拦截（路由层拦截），所以这里能成功
    assert result is not None


# -----------------------------------------------------------------------
# API 层锁定测试
# -----------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """创建测试 HTTP 客户端"""
    from httpx import ASGITransport, AsyncClient as HttpxAsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.main import app
    from app.models.core import User, UserRole

    # 创建测试用户
    test_user = User(
        id=FAKE_USER_ID,
        username="test_admin",
        email="test@example.com",
        hashed_password="fake",
        role=UserRole.admin,
        is_active=True,
        is_deleted=False,
    )
    db_session.add(test_user)
    await db_session.flush()

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with HttpxAsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_update_paragraph_blocked_eqcr_approved(
    db_session: AsyncSession, client
):
    """PUT /api/audit-report/{id}/paragraphs/{section} 在 eqcr_approved 态返回 403"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.eqcr_approved)
    await db_session.commit()

    resp = await client.put(
        f"/api/audit-report/{report.id}/paragraphs/审计意见段",
        json={"section_name": "审计意见段", "content": "尝试修改"},
    )
    assert resp.status_code == 403
    data = resp.json()
    # Response middleware wraps as {code, message} or {detail}
    detail = data.get("message", data.get("detail", data))
    if isinstance(detail, dict):
        assert detail.get("error_code") == "OPINION_LOCKED_BY_EQCR"
    else:
        assert "EQCR" in str(detail)


@pytest.mark.asyncio
async def test_api_update_paragraph_blocked_final(db_session: AsyncSession, client):
    """PUT /api/audit-report/{id}/paragraphs/{section} 在 final 态返回 403"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.final)
    await db_session.commit()

    resp = await client.put(
        f"/api/audit-report/{report.id}/paragraphs/审计意见段",
        json={"section_name": "审计意见段", "content": "尝试修改"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_update_paragraph_allowed_draft(db_session: AsyncSession, client):
    """PUT /api/audit-report/{id}/paragraphs/{section} 在 draft 态允许修改"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.draft)
    await db_session.commit()

    resp = await client.put(
        f"/api/audit-report/{report.id}/paragraphs/审计意见段",
        json={"section_name": "审计意见段", "content": "新内容"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_update_paragraph_allowed_review(db_session: AsyncSession, client):
    """PUT /api/audit-report/{id}/paragraphs/{section} 在 review 态允许修改"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.review)
    await db_session.commit()

    resp = await client.put(
        f"/api/audit-report/{report.id}/paragraphs/审计意见段",
        json={"section_name": "审计意见段", "content": "新内容"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_generate_report_blocked_eqcr_approved(
    db_session: AsyncSession, client
):
    """POST /api/audit-report/generate 在 eqcr_approved 态返回 403"""
    await _create_project(db_session)
    await _create_report(db_session, status=ReportStatus.eqcr_approved)
    await db_session.commit()

    resp = await client.post(
        "/api/audit-report/generate",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2025,
            "opinion_type": "qualified",
            "company_type": "non_listed",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    detail = data.get("message", data.get("detail", data))
    if isinstance(detail, dict):
        assert detail.get("error_code") == "OPINION_LOCKED_BY_EQCR"


@pytest.mark.asyncio
async def test_api_update_status_blocked_eqcr_approved_to_review(
    db_session: AsyncSession, client
):
    """PUT /api/audit-report/{id}/status 在 eqcr_approved 态不允许回退到 review"""
    await _create_project(db_session)
    report = await _create_report(db_session, status=ReportStatus.eqcr_approved)
    await db_session.commit()

    resp = await client.put(
        f"/api/audit-report/{report.id}/status",
        json={"status": "review"},
    )
    assert resp.status_code == 403
    data = resp.json()
    detail = data.get("message", data.get("detail", data))
    if isinstance(detail, dict):
        assert detail.get("error_code") == "OPINION_LOCKED_BY_EQCR"
