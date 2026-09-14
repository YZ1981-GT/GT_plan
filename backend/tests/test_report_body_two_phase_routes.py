"""report-body 两阶段路由测试 — audit-report-template-integration task 8.5.

覆盖：
  - 权限矩阵：export 权限不足（readonly）→ preview/confirm 均 403
  - 权限矩阵：manager 有 export 权限可通过 guard
  - 过期 preview_session → confirm 返回 404
  - 不存在 preview_session → confirm 返回 404
  - 他人 preview_session → confirm 返回 403

直接调用路由函数（in-process，无需 uvicorn）。guard 在模板解析前执行，
confirm 在交付件入库前校验会话，故无需真实模板即可覆盖以上分支。

Feature: audit-report-template-integration
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.report_models import FillPreviewSession
from app.models.phase13_schemas import (
    ReportBodyConfirmRequest,
    ReportBodyPreviewRequest,
)
from app.routers.deliverable import confirm_report_body, preview_report_body

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, role: UserRole) -> User:
    uid = uuid.uuid4()
    suffix = uid.hex[:8]
    user = User(
        id=uid,
        username=f"u_{suffix}",
        email=f"u_{suffix}@test.com",
        hashed_password="x",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_project(db: AsyncSession, owner_id: uuid.UUID) -> Project:
    pid = uuid.uuid4()
    project = Project(
        id=pid,
        name="两阶段测试项目",
        client_name="客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=owner_id,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_session_row(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
) -> FillPreviewSession:
    sess = FillPreviewSession(
        project_id=project_id,
        user_id=user_id,
        year=2025,
        opinion_type="unqualified",
        company_subtype="type_d",
        template_variant="simple",
        template_version="test-v1",
        working_path="/tmp/nonexistent/working.docx",
        expires_at=expires_at,
    )
    db.add(sess)
    await db.flush()
    return sess


# ───────────────────────── 权限矩阵 ─────────────────────────


@pytest.mark.asyncio
async def test_preview_readonly_forbidden(db_session):
    """readonly 无 export 权限 → preview 403。"""
    user = await _make_user(db_session, UserRole.readonly)
    project = await _make_project(db_session, user.id)
    body = ReportBodyPreviewRequest(
        year=2025, opinion_type="unqualified", company_subtype="type_d"
    )
    with pytest.raises(HTTPException) as exc:
        await preview_report_body(
            project.id, body, db=db_session, current_user=user
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_readonly_forbidden(db_session):
    """readonly 无 export 权限 → confirm 403（在校验会话前即被 guard 拦截）。"""
    user = await _make_user(db_session, UserRole.readonly)
    project = await _make_project(db_session, user.id)
    body = ReportBodyConfirmRequest(
        year=2025, preview_session_id=uuid.uuid4(), optional_sections={}
    )
    with pytest.raises(HTTPException) as exc:
        await confirm_report_body(
            project.id, body, db=db_session, current_user=user
        )
    assert exc.value.status_code == 403


# ───────────────────────── 过期 / 缺失 / 他人会话 ─────────────────────────


@pytest.mark.asyncio
async def test_confirm_expired_session_404(db_session):
    """过期 preview_session → confirm 404。"""
    user = await _make_user(db_session, UserRole.manager)
    project = await _make_project(db_session, user.id)
    sess = await _make_session_row(
        db_session,
        project_id=project.id,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    body = ReportBodyConfirmRequest(
        year=2025, preview_session_id=sess.id, optional_sections={"emphasis": False}
    )
    with pytest.raises(HTTPException) as exc:
        await confirm_report_body(
            project.id, body, db=db_session, current_user=user
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_missing_session_404(db_session):
    """不存在的 preview_session → confirm 404。"""
    user = await _make_user(db_session, UserRole.manager)
    project = await _make_project(db_session, user.id)
    body = ReportBodyConfirmRequest(
        year=2025, preview_session_id=uuid.uuid4(), optional_sections={}
    )
    with pytest.raises(HTTPException) as exc:
        await confirm_report_body(
            project.id, body, db=db_session, current_user=user
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_wrong_user_403(db_session):
    """他人 preview_session（user 不匹配）→ confirm 403。"""
    owner = await _make_user(db_session, UserRole.manager)
    other = await _make_user(db_session, UserRole.manager)
    project = await _make_project(db_session, owner.id)
    sess = await _make_session_row(
        db_session,
        project_id=project.id,
        user_id=owner.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    body = ReportBodyConfirmRequest(
        year=2025, preview_session_id=sess.id, optional_sections={}
    )
    with pytest.raises(HTTPException) as exc:
        await confirm_report_body(
            project.id, body, db=db_session, current_user=other
        )
    assert exc.value.status_code == 403
