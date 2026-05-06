"""budget_alert_worker 主循环测试 — Round 2 Batch 2 P2 测试覆盖

验证:
- _check_all_projects 在 80% 阈值时触发通知
- 幂等键防止重复发送

Validates: Refinement Round 2 复盘 P2 测试覆盖第 4 项
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, ProjectStatus, ProjectType
from app.models.core import Notification, Project
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)

MGR_USER_ID = uuid.uuid4()
PARTNER_USER_ID = uuid.uuid4()
MGR_STAFF_ID = uuid.uuid4()
PARTNER_STAFF_ID = uuid.uuid4()
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
async def seeded_80pct(db_session: AsyncSession):
    """项目预算 100h，已批准 85h（>80%），应触发 budget_alert_80。"""
    proj = Project(
        id=PROJECT_ID, name="预算预警项目", client_name="客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        budget_hours=100, created_by=MGR_USER_ID,
    )
    db_session.add(proj)
    await db_session.flush()

    mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="经理", title="经理")
    partner = StaffMember(id=PARTNER_STAFF_ID, user_id=PARTNER_USER_ID, name="合伙人", title="合伙人")
    db_session.add_all([mgr, partner])
    await db_session.flush()

    db_session.add_all([
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=MGR_STAFF_ID, role="manager"),
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=PARTNER_STAFF_ID, role="signing_partner"),
    ])
    await db_session.flush()

    # 85h 已批准工时
    today = date.today()
    for i in range(17):
        db_session.add(WorkHour(
            id=uuid.uuid4(), staff_id=MGR_STAFF_ID, project_id=PROJECT_ID,
            work_date=today, hours=Decimal("5"), status="approved",
        ))
    await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def seeded_50pct(db_session: AsyncSession):
    """项目预算 100h，已批准 50h（<80%），不应触发通知。"""
    proj = Project(
        id=PROJECT_ID, name="正常项目", client_name="客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        budget_hours=100, created_by=MGR_USER_ID,
    )
    db_session.add(proj)
    await db_session.flush()

    mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="经理", title="经理")
    db_session.add(mgr)
    await db_session.flush()

    db_session.add(ProjectAssignment(
        id=uuid.uuid4(), project_id=PROJECT_ID,
        staff_id=MGR_STAFF_ID, role="manager",
    ))
    await db_session.flush()

    # 50h 已批准工时
    today = date.today()
    for i in range(10):
        db_session.add(WorkHour(
            id=uuid.uuid4(), staff_id=MGR_STAFF_ID, project_id=PROJECT_ID,
            work_date=today, hours=Decimal("5"), status="approved",
        ))
    await db_session.commit()
    return db_session


class _FakeRedis:
    """模拟 Redis 客户端，支持 get/set。"""

    def __init__(self, store: dict[str, str] | None = None):
        self._store: dict[str, str] = store or {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value


def _make_session_factory(db_session: AsyncSession):
    """创建一个返回测试 session 的 async context manager factory。"""
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


class TestCheckAllProjects:
    """_check_all_projects 主循环测试。"""

    @pytest.mark.asyncio
    async def test_80pct_threshold_triggers_notification(self, seeded_80pct):
        """85% 利用率应触发 budget_alert_80 通知。"""
        import sqlalchemy as sa

        fake_redis = _FakeRedis()
        session_factory = _make_session_factory(seeded_80pct)

        with patch("app.core.database.async_session", session_factory), \
             patch("app.core.redis.redis_client", fake_redis):
            from app.workers.budget_alert_worker import _check_all_projects
            await _check_all_projects()

        # 验证通知已写入
        result = await seeded_80pct.execute(
            sa.select(Notification).where(
                Notification.message_type == "budget_alert_80",
            )
        )
        notifications = result.scalars().all()
        # 应发给 manager + signing_partner = 2 人
        assert len(notifications) == 2

        # 验证幂等键已设置
        today_str = date.today().strftime("%Y%m%d")
        idem_key = f"budget_alert:{PROJECT_ID}:80:{today_str}"
        assert fake_redis._store.get(idem_key) == "1"

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate(self, seeded_80pct):
        """幂等键存在时不重复发送通知。"""
        import sqlalchemy as sa

        # 预设幂等键
        today_str = date.today().strftime("%Y%m%d")
        initial_store = {
            f"budget_alert:{PROJECT_ID}:80:{today_str}": "1",
        }
        fake_redis = _FakeRedis(store=initial_store)
        session_factory = _make_session_factory(seeded_80pct)

        with patch("app.core.database.async_session", session_factory), \
             patch("app.core.redis.redis_client", fake_redis):
            from app.workers.budget_alert_worker import _check_all_projects
            await _check_all_projects()

        # 不应有新通知（幂等键阻止）
        result = await seeded_80pct.execute(
            sa.select(Notification).where(
                Notification.message_type == "budget_alert_80",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_below_threshold_no_notification(self, seeded_50pct):
        """50% 利用率不应触发任何通知。"""
        import sqlalchemy as sa

        fake_redis = _FakeRedis()
        session_factory = _make_session_factory(seeded_50pct)

        with patch("app.core.database.async_session", session_factory), \
             patch("app.core.redis.redis_client", fake_redis):
            from app.workers.budget_alert_worker import _check_all_projects
            await _check_all_projects()

        # 不应有通知
        result = await seeded_50pct.execute(
            sa.select(Notification).where(
                Notification.message_type.in_(["budget_alert_80", "budget_overrun"]),
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_100pct_triggers_overrun_notification(self, db_session):
        """100%+ 利用率应触发 budget_overrun 通知。"""
        import sqlalchemy as sa

        # 创建 105% 利用率的项目
        proj = Project(
            id=PROJECT_ID, name="超支项目", client_name="客户",
            project_type=ProjectType.annual, status=ProjectStatus.execution,
            budget_hours=100, created_by=MGR_USER_ID,
        )
        db_session.add(proj)
        await db_session.flush()

        mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="经理", title="经理")
        db_session.add(mgr)
        await db_session.flush()

        db_session.add(ProjectAssignment(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            staff_id=MGR_STAFF_ID, role="manager",
        ))
        await db_session.flush()

        # 105h 已批准工时
        today = date.today()
        for i in range(21):
            db_session.add(WorkHour(
                id=uuid.uuid4(), staff_id=MGR_STAFF_ID, project_id=PROJECT_ID,
                work_date=today, hours=Decimal("5"), status="approved",
            ))
        await db_session.commit()

        fake_redis = _FakeRedis()
        session_factory = _make_session_factory(db_session)

        with patch("app.core.database.async_session", session_factory), \
             patch("app.core.redis.redis_client", fake_redis):
            from app.workers.budget_alert_worker import _check_all_projects
            await _check_all_projects()

        # 应有 budget_overrun 通知
        result = await db_session.execute(
            sa.select(Notification).where(
                Notification.message_type == "budget_overrun",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) >= 1

        # 也应有 budget_alert_80 通知（因为 105% > 80%）
        result2 = await db_session.execute(
            sa.select(Notification).where(
                Notification.message_type == "budget_alert_80",
            )
        )
        notifications_80 = result2.scalars().all()
        assert len(notifications_80) >= 1
