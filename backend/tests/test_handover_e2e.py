"""Sprint 3 端到端集成测试 — 人员交接 (Batch 1 P0.6)

验证链路：建 staff → 分底稿/工单 → 离职交接 → 验证数据全迁移+留痕
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Notification, Project
from app.models.handover_models import HandoverRecord
from app.models.independence_models import IndependenceDeclaration
from app.models.phase15_models import IssueTicket
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
)
from app.routers.staff import router as staff_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


class _FakeUser:
    def __init__(self, uid, role=UserRole.admin):
        self.id = uid
        self.username = "admin"
        self.email = "a@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


ADMIN_ID = uuid.uuid4()
FROM_STAFF = uuid.uuid4()
TO_STAFF = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    # 项目
    proj = Project(
        id=PROJECT_ID, name="归档项目", client_name="客户 H",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=ADMIN_ID,
    )
    db_session.add(proj)

    # Staff
    from_s = StaffMember(id=FROM_STAFF, user_id=FROM_STAFF, name="离职员工", title="审计员")
    to_s = StaffMember(id=TO_STAFF, user_id=TO_STAFF, name="接收员工", title="审计员")
    db_session.add_all([from_s, to_s])
    await db_session.flush()

    # 2 张底稿分配给 from_staff
    for i in range(2):
        wp_idx = WpIndex(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            wp_code=f"H-{i}", wp_name=f"底稿 {i}",
            audit_cycle="D", status=WpStatus.not_started,
        )
        db_session.add(wp_idx)
        await db_session.flush()
        wp = WorkingPaper(
            id=uuid.uuid4(), project_id=PROJECT_ID, wp_index_id=wp_idx.id,
            file_path=f"/tmp/h{i}.xlsx", source_type=WpSourceType.template,
            status=WpFileStatus.draft, assigned_to=FROM_STAFF, file_version=1,
        )
        db_session.add(wp)

    # 1 张 open 工单给 from_staff
    db_session.add(IssueTicket(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        source="L2", severity="major", category="data_mismatch",
        title="待处理问题", owner_id=FROM_STAFF,
        status="open", trace_id=str(uuid.uuid4()),
    ))

    # 1 个 project assignment for from_staff
    db_session.add(ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        staff_id=FROM_STAFF, role="auditor",
    ))

    # 1 个 draft 独立性声明
    db_session.add(IndependenceDeclaration(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        declarant_id=FROM_STAFF, declaration_year=2026,
        status="draft",
    ))

    await db_session.commit()


def _app(db_session: AsyncSession):
    app = FastAPI()
    app.include_router(staff_router)

    fake = _FakeUser(ADMIN_ID, role=UserRole.admin)

    async def _db():
        yield db_session

    async def _u():
        return fake

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _u
    app.dependency_overrides[require_role(["admin", "partner", "manager"])] = _u
    return app


@pytest.mark.asyncio
@patch("app.services.handover_service.audit_logger.log_action", new_callable=AsyncMock)
async def test_resignation_handover_e2e(mock_log, db_session, seeded):
    """离职交接：底稿/工单/委派全部迁移，独立性声明被 supersede，留痕在 HandoverRecord。"""
    app = _app(db_session)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # 预览
        resp = await c.get(
            f"/api/staff/{FROM_STAFF}/handover/preview",
            params={"scope": "all"},
        )
        assert resp.status_code == 200, resp.text
        preview = resp.json()
        assert preview["workpapers"] == 2
        assert preview["issues"] == 1
        assert preview["assignments"] == 1

        # 执行离职交接
        resp = await c.post(
            f"/api/staff/{FROM_STAFF}/handover",
            json={
                "scope": "all",
                "target_staff_id": str(TO_STAFF),
                "reason_code": "resignation",
                "reason_detail": "离职",
                "effective_date": str(date.today()),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["workpapers_moved"] == 2
        assert data["issues_moved"] == 1
        assert data["assignments_moved"] == 1
        assert data["independence_superseded"] == 1
        assert data["handover_record_id"]

    # grep 核查：DB 数据真迁移
    wps = (await db_session.execute(sa.select(WorkingPaper))).scalars().all()
    for wp in wps:
        assert wp.assigned_to == TO_STAFF

    ticket = (await db_session.execute(sa.select(IssueTicket))).scalar_one()
    assert ticket.owner_id == TO_STAFF

    # ProjectAssignment 软删除 from + 新增 to
    pas = (await db_session.execute(sa.select(ProjectAssignment))).scalars().all()
    from_pa = [p for p in pas if p.staff_id == FROM_STAFF]
    to_pa = [p for p in pas if p.staff_id == TO_STAFF and not p.is_deleted]
    assert all(p.is_deleted for p in from_pa)
    assert len(to_pa) == 1

    # IndependenceDeclaration status 变 superseded
    decl = (await db_session.execute(sa.select(IndependenceDeclaration))).scalar_one()
    assert decl.status == "superseded_by_handover"

    # HandoverRecord 留痕
    record = (await db_session.execute(sa.select(HandoverRecord))).scalar_one()
    assert record.from_staff_id == FROM_STAFF
    assert record.to_staff_id == TO_STAFF
    assert record.reason_code == "resignation"

    # audit_log 被调用
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["action"] == "staff_handover"

    # 新负责人收到 handover_received 通知
    notifs = (await db_session.execute(sa.select(Notification).where(
        Notification.recipient_id == TO_STAFF,
        Notification.message_type == "handover_received",
    ))).scalars().all()
    assert len(notifs) == 1
