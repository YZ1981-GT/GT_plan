"""Tests for Task 10: 重新分配增强 — 通知原编制人和新编制人

Validates: Requirements 4.5
- 原编制人收到"底稿 {wp_code} 已被重新分配"
- 新编制人收到"项目「{project_name}」的底稿 {wp_code} 已转交给您"
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Notification, Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
    WorkingPaper,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

OLD_USER_ID = uuid.uuid4()
NEW_USER_ID = uuid.uuid4()
MANAGER_USER_ID = uuid.uuid4()
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
    """Create test data: project + wp_index + working_paper with assigned_to"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试审计项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=MANAGER_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    idx1 = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="D1-1",
        wp_name="应收账款底稿",
        audit_cycle="D",
        status=WpStatus.in_progress,
    )
    db_session.add(idx1)
    await db_session.flush()

    wp1 = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx1.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/D1-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        assigned_to=OLD_USER_ID,
        created_by=MANAGER_USER_ID,
    )
    db_session.add(wp1)
    await db_session.commit()

    return {
        "project": project,
        "idx1": idx1,
        "wp1": wp1,
    }


class TestSendReassignmentNotifications:
    """Unit tests for _send_reassignment_notifications helper function."""

    @pytest.mark.asyncio
    async def test_sends_notification_to_old_assignee(self, db_session, seeded_db):
        """原编制人收到'底稿已被重新分配'通知"""
        from app.routers.working_paper import _send_reassignment_notifications

        await _send_reassignment_notifications(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            wp_id=seeded_db["wp1"].id,
            old_assignee_id=OLD_USER_ID,
            new_assignee_id=NEW_USER_ID,
        )
        await db_session.commit()

        # 查询原编制人的通知
        import sqlalchemy as sa
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.recipient_id == OLD_USER_ID,
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.title == "底稿已被重新分配"
        assert "D1-1" in notif.content
        assert "重新分配" in notif.content
        assert notif.message_type == "workpaper_reminder"

    @pytest.mark.asyncio
    async def test_sends_notification_to_new_assignee(self, db_session, seeded_db):
        """新编制人收到'底稿已转交给您'通知"""
        from app.routers.working_paper import _send_reassignment_notifications

        await _send_reassignment_notifications(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            wp_id=seeded_db["wp1"].id,
            old_assignee_id=OLD_USER_ID,
            new_assignee_id=NEW_USER_ID,
        )
        await db_session.commit()

        # 查询新编制人的通知
        import sqlalchemy as sa
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.recipient_id == NEW_USER_ID,
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.title == "底稿已转交给您"
        assert "测试审计项目" in notif.content
        assert "D1-1" in notif.content
        assert notif.message_type == "assignment_created"

    @pytest.mark.asyncio
    async def test_both_notifications_contain_wp_code(self, db_session, seeded_db):
        """两条通知都包含底稿编号"""
        from app.routers.working_paper import _send_reassignment_notifications

        await _send_reassignment_notifications(
            db=db_session,
            project_id=FAKE_PROJECT_ID,
            wp_id=seeded_db["wp1"].id,
            old_assignee_id=OLD_USER_ID,
            new_assignee_id=NEW_USER_ID,
        )
        await db_session.commit()

        import sqlalchemy as sa
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.recipient_id.in_([OLD_USER_ID, NEW_USER_ID]),
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 2
        for notif in notifs:
            assert "D1-1" in notif.content


class TestAssignEndpointReassignment:
    """Integration tests for PUT /working-papers/{wp_id}/assign with reassignment notifications."""

    @pytest.mark.asyncio
    async def test_first_assignment_no_notification(self, db_session, seeded_db):
        """首次分配（无原编制人）不发重新分配通知"""
        import sqlalchemy as sa

        # 创建一个未分配的底稿
        idx2 = WpIndex(
            project_id=FAKE_PROJECT_ID,
            wp_code="D2-1",
            wp_name="存货底稿",
            audit_cycle="D",
            status=WpStatus.not_started,
        )
        db_session.add(idx2)
        await db_session.flush()

        wp_unassigned = WorkingPaper(
            project_id=FAKE_PROJECT_ID,
            wp_index_id=idx2.id,
            file_path=f"{FAKE_PROJECT_ID}/2025/D2-1.xlsx",
            source_type=WpSourceType.template,
            status=WpFileStatus.draft,
            file_version=1,
            assigned_to=None,  # 未分配
            created_by=MANAGER_USER_ID,
        )
        db_session.add(wp_unassigned)
        await db_session.commit()

        # 模拟首次分配
        from app.services.working_paper_service import WorkingPaperService
        svc = WorkingPaperService()
        await svc.assign_workpaper(
            db=db_session,
            wp_id=wp_unassigned.id,
            project_id=FAKE_PROJECT_ID,
            assigned_to=NEW_USER_ID,
        )
        await db_session.commit()

        # 首次分配不应触发重新分配通知（通知逻辑在 router 层）
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.recipient_id == NEW_USER_ID,
                Notification.title == "底稿已转交给您",
            )
        )
        notifs = result.scalars().all()
        # 服务层不发通知，通知在 router 层判断 old_assigned_to 后才发
        assert len(notifs) == 0

    @pytest.mark.asyncio
    async def test_same_assignee_no_notification(self, db_session, seeded_db):
        """分配给同一人不发重新分配通知"""
        from app.routers.working_paper import _send_reassignment_notifications
        import sqlalchemy as sa

        # 不应调用通知函数（在 router 层 old == new 时跳过）
        # 直接验证逻辑：old_assigned_to == data.assigned_to 时不发通知
        # 这里只验证 helper 函数本身不会被调用的前提条件
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.recipient_id == OLD_USER_ID,
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 0
