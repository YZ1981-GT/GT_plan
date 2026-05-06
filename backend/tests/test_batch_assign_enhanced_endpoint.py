"""batch_assign_enhanced 端点集成测试 — Round 2 Batch 2 P2 测试覆盖

验证:
- 成功分配（manual 策略）+ DB 变更 + 通知发送
- 跨项目底稿拒绝（400）
- 非授权经理拒绝（403）

Validates: Refinement Round 2 复盘 P2 测试覆盖第 1 项
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Notification, Project
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.batch_assign_enhanced import router as bae_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


class _FakeUser:
    def __init__(self, uid, role=UserRole.admin):
        self.id = uid
        self.username = "test_user"
        self.email = "test@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


MGR_USER_ID = uuid.uuid4()
AUD_USER_ID = uuid.uuid4()
STRANGER_USER_ID = uuid.uuid4()
MGR_STAFF_ID = uuid.uuid4()
AUD_STAFF_ID = uuid.uuid4()
STRANGER_STAFF_ID = uuid.uuid4()
PROJECT_A_ID = uuid.uuid4()
PROJECT_B_ID = uuid.uuid4()


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
    """两个项目，MGR 管理 A，不管理 B。"""
    proj_a = Project(
        id=PROJECT_A_ID, name="项目 A", client_name="客户 A",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=MGR_USER_ID,
    )
    proj_b = Project(
        id=PROJECT_B_ID, name="项目 B", client_name="客户 B",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=uuid.uuid4(),
    )
    db_session.add_all([proj_a, proj_b])
    await db_session.flush()

    mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="张经理", title="经理")
    aud = StaffMember(id=AUD_STAFF_ID, user_id=AUD_USER_ID, name="李审计", title="审计员")
    stranger = StaffMember(id=STRANGER_STAFF_ID, user_id=STRANGER_USER_ID, name="路人", title="审计员")
    db_session.add_all([mgr, aud, stranger])
    await db_session.flush()

    db_session.add_all([
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_A_ID,
                          staff_id=MGR_STAFF_ID, role="manager"),
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_A_ID,
                          staff_id=AUD_STAFF_ID, role="auditor"),
        # stranger 只在 B 项目
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_B_ID,
                          staff_id=STRANGER_STAFF_ID, role="auditor"),
    ])
    await db_session.flush()

    # 项目 A 的底稿
    idx1 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-001",
                   wp_name="底稿 1", audit_cycle="D循环", status=WpStatus.in_progress)
    idx2 = WpIndex(id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_code="A-002",
                   wp_name="底稿 2", audit_cycle="F循环", status=WpStatus.in_progress)
    db_session.add_all([idx1, idx2])
    await db_session.flush()

    wp1 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx1.id,
        file_path="/tmp/1.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    wp2 = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_A_ID, wp_index_id=idx2.id,
        file_path="/tmp/2.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    db_session.add_all([wp1, wp2])
    await db_session.flush()

    # 项目 B 的底稿
    idx_b = WpIndex(id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_code="B-001",
                    wp_name="底稿 B1", audit_cycle="K循环", status=WpStatus.in_progress)
    db_session.add(idx_b)
    await db_session.flush()

    wp_b = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_B_ID, wp_index_id=idx_b.id,
        file_path="/tmp/b1.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    db_session.add(wp_b)
    await db_session.commit()

    return {
        "wp1_id": wp1.id,
        "wp2_id": wp2.id,
        "wp_b_id": wp_b.id,
    }


def _make_client(db_session: AsyncSession, user_id: uuid.UUID, role: UserRole = UserRole.admin) -> AsyncClient:
    app = FastAPI()
    app.include_router(bae_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(user_id, role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestBatchAssignEnhancedEndpoint:
    """POST /api/workpapers/batch-assign-enhanced"""

    @pytest.mark.asyncio
    async def test_successful_manual_assignment(self, db_session, seeded):
        """manual 策略成功分配 + 通知发送。"""
        wp1_id = seeded["wp1_id"]
        wp2_id = seeded["wp2_id"]

        with patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock):
            async with _make_client(db_session, MGR_USER_ID, UserRole.admin) as client:
                resp = await client.post("/api/workpapers/batch-assign-enhanced", json={
                    "wp_ids": [str(wp1_id), str(wp2_id)],
                    "strategy": "manual",
                    "candidates": [str(AUD_USER_ID)],
                })

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 2
        assert body["notifications_sent"] >= 1
        assert len(body["assignments"]) == 2
        # 所有底稿分配给同一人
        for a in body["assignments"]:
            assert a["user_id"] == str(AUD_USER_ID)

    @pytest.mark.asyncio
    async def test_notification_sent_on_assignment(self, db_session, seeded):
        """分配后通知记录写入 DB。"""
        import sqlalchemy as sa

        wp1_id = seeded["wp1_id"]

        with patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock):
            async with _make_client(db_session, MGR_USER_ID, UserRole.admin) as client:
                resp = await client.post("/api/workpapers/batch-assign-enhanced", json={
                    "wp_ids": [str(wp1_id)],
                    "strategy": "manual",
                    "candidates": [str(AUD_USER_ID)],
                })

        assert resp.status_code == 200

        # 验证通知写入
        notif_q = sa.select(Notification).where(
            Notification.recipient_id == AUD_USER_ID,
            Notification.message_type == "assignment_created",
        )
        result = await db_session.execute(notif_q)
        notifs = result.scalars().all()
        assert len(notifs) >= 1

    @pytest.mark.asyncio
    async def test_cross_project_rejection(self, db_session, seeded):
        """跨项目底稿应返回 400。"""
        wp1_id = seeded["wp1_id"]
        wp_b_id = seeded["wp_b_id"]

        with patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock):
            async with _make_client(db_session, MGR_USER_ID, UserRole.admin) as client:
                resp = await client.post("/api/workpapers/batch-assign-enhanced", json={
                    "wp_ids": [str(wp1_id), str(wp_b_id)],
                    "strategy": "manual",
                    "candidates": [str(AUD_USER_ID)],
                })

        assert resp.status_code == 400
        assert "同一项目" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unauthorized_manager_rejection(self, db_session, seeded):
        """非项目经理/签字合伙人应返回 403。"""
        wp1_id = seeded["wp1_id"]

        with patch("app.services.audit_logger_enhanced.audit_logger.log_action", new_callable=AsyncMock):
            async with _make_client(db_session, STRANGER_USER_ID, UserRole.manager) as client:
                resp = await client.post("/api/workpapers/batch-assign-enhanced", json={
                    "wp_ids": [str(wp1_id)],
                    "strategy": "manual",
                    "candidates": [str(AUD_USER_ID)],
                })

        assert resp.status_code == 403
        assert "权限不足" in resp.json()["detail"]
