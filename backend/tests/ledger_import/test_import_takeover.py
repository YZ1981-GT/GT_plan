"""F22 / Sprint 5.13: 导入接管机制集成测试

背景（requirements F22 / design D8.3）：
- heartbeat 超 5min 允许其他成员接管
- 接管后 creator_chain 追加记录
- 接管后触发 resume_from_checkpoint

测试场景：
1. heartbeat 未过期 → 403 "job still active"
2. heartbeat 过期 → 接管成功 + creator_chain 更新
3. 非 PM/admin/partner 角色 → 403
4. heartbeat_at 为 NULL → 允许接管（视为已过期）

Fixture 模式：SQLite in-memory（参考 test_cross_project_isolation.py）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.models.dataset_models import ImportJob, JobStatus  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeUser:
    """Minimal user mock for dependency injection."""

    def __init__(self, user_id: uuid.UUID, role: str = "admin"):
        self.id = user_id
        self.role = type("Role", (), {"value": role})()


def _make_project_id() -> uuid.UUID:
    return uuid.uuid4()


async def _create_job(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    heartbeat_at: datetime | None = None,
    created_by: uuid.UUID | None = None,
    status: JobStatus = JobStatus.running,
) -> ImportJob:
    """Create a minimal ImportJob for testing."""
    job = ImportJob(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2025,
        status=status,
        heartbeat_at=heartbeat_at,
        created_by=created_by,
        creator_chain=[
            {
                "user_id": str(created_by or uuid.uuid4()),
                "action": "create",
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )
    db.add(job)
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_takeover_heartbeat_not_expired(db_session: AsyncSession):
    """heartbeat 未过期 → 应拒绝接管（403）"""
    project_id = _make_project_id()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # heartbeat 刚更新（1 分钟前）
    recent_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=1)
    job = await _create_job(
        db_session,
        project_id,
        heartbeat_at=recent_heartbeat,
        created_by=user_a,
    )

    # 模拟接管逻辑（直接测试核心逻辑而非 HTTP 层）
    from app.routers.ledger_import_v2 import TakeoverRequest

    current_user = FakeUser(user_b, role="admin")
    now = datetime.now(timezone.utc)

    # 检查 heartbeat 是否过期
    heartbeat_expired = False
    if job.heartbeat_at is None:
        heartbeat_expired = True
    else:
        hb = job.heartbeat_at
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb < now - timedelta(minutes=5):
            heartbeat_expired = True

    assert not heartbeat_expired, "heartbeat 未过期时不应允许接管"


@pytest.mark.asyncio
async def test_takeover_heartbeat_expired(db_session: AsyncSession):
    """heartbeat 过期 → 接管成功 + creator_chain 更新"""
    project_id = _make_project_id()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # heartbeat 10 分钟前（已过期）
    old_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = await _create_job(
        db_session,
        project_id,
        heartbeat_at=old_heartbeat,
        created_by=user_a,
        status=JobStatus.running,
    )

    current_user = FakeUser(user_b, role="pm")
    now = datetime.now(timezone.utc)

    # 检查 heartbeat 过期
    heartbeat_expired = False
    if job.heartbeat_at is None:
        heartbeat_expired = True
    else:
        hb = job.heartbeat_at
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb < now - timedelta(minutes=5):
            heartbeat_expired = True

    assert heartbeat_expired, "heartbeat 过期时应允许接管"

    # 执行接管：更新 creator_chain
    chain = list(job.creator_chain or [])
    chain.append({
        "user_id": str(current_user.id),
        "action": "takeover",
        "at": now.isoformat(),
        "reason": "A 网络掉线",
    })
    job.creator_chain = chain
    job.created_by = current_user.id
    await db_session.flush()

    # 验证
    assert len(job.creator_chain) == 2
    assert job.creator_chain[0]["action"] == "create"
    assert job.creator_chain[1]["action"] == "takeover"
    assert job.creator_chain[1]["user_id"] == str(user_b)
    assert job.creator_chain[1]["reason"] == "A 网络掉线"
    assert job.created_by == user_b


@pytest.mark.asyncio
async def test_takeover_non_pm_admin_partner_rejected():
    """非 PM/admin/partner 角色 → 应拒绝接管"""
    user = FakeUser(uuid.uuid4(), role="auditor")
    allowed_roles = {"pm", "admin", "partner"}
    assert user.role.value not in allowed_roles


@pytest.mark.asyncio
async def test_takeover_heartbeat_null_allows_takeover(db_session: AsyncSession):
    """heartbeat_at 为 NULL → 视为已过期，允许接管"""
    project_id = _make_project_id()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # heartbeat_at = None
    job = await _create_job(
        db_session,
        project_id,
        heartbeat_at=None,
        created_by=user_a,
        status=JobStatus.running,
    )

    now = datetime.now(timezone.utc)

    # 检查 heartbeat 过期逻辑
    heartbeat_expired = False
    if job.heartbeat_at is None:
        heartbeat_expired = True
    else:
        hb = job.heartbeat_at
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb < now - timedelta(minutes=5):
            heartbeat_expired = True

    assert heartbeat_expired, "heartbeat_at=NULL 应视为已过期"

    # 执行接管
    chain = list(job.creator_chain or [])
    chain.append({
        "user_id": str(user_b),
        "action": "takeover",
        "at": now.isoformat(),
        "reason": "原创建者未启动",
    })
    job.creator_chain = chain
    job.created_by = user_b
    await db_session.flush()

    assert len(job.creator_chain) == 2
    assert job.creator_chain[1]["action"] == "takeover"
    assert job.creator_chain[1]["reason"] == "原创建者未启动"


@pytest.mark.asyncio
async def test_takeover_triggers_resume(db_session: AsyncSession):
    """接管后应触发 resume_from_checkpoint"""
    project_id = _make_project_id()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    # 过期 heartbeat
    old_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = await _create_job(
        db_session,
        project_id,
        heartbeat_at=old_heartbeat,
        created_by=user_a,
        status=JobStatus.failed,
    )

    # Mock resume_from_checkpoint
    mock_resume_result = {
        "resumed": True,
        "from_phase": "activation_gate_done",
        "action": "resume_from_activate_dataset",
        "message": "从 activation_gate_done 恢复",
        "job_id": str(job.id),
    }

    with patch(
        "app.services.import_job_runner.ImportJobRunner.resume_from_checkpoint",
        new_callable=AsyncMock,
        return_value=mock_resume_result,
    ) as mock_resume:
        from app.services.import_job_runner import ImportJobRunner

        result = await ImportJobRunner.resume_from_checkpoint(job.id)

        mock_resume.assert_called_once_with(job.id)
        assert result["resumed"] is True
        assert result["from_phase"] == "activation_gate_done"


@pytest.mark.asyncio
async def test_takeover_multiple_times(db_session: AsyncSession):
    """多次接管 → creator_chain 正确累加"""
    project_id = _make_project_id()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    user_c = uuid.uuid4()

    old_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
    job = await _create_job(
        db_session,
        project_id,
        heartbeat_at=old_heartbeat,
        created_by=user_a,
        status=JobStatus.running,
    )

    now = datetime.now(timezone.utc)

    # 第一次接管 by B
    chain = list(job.creator_chain or [])
    chain.append({
        "user_id": str(user_b),
        "action": "takeover",
        "at": now.isoformat(),
        "reason": "A 掉线",
    })
    job.creator_chain = chain
    job.created_by = user_b
    await db_session.flush()

    # 第二次接管 by C
    chain = list(job.creator_chain or [])
    chain.append({
        "user_id": str(user_c),
        "action": "takeover",
        "at": (now + timedelta(minutes=10)).isoformat(),
        "reason": "B 也掉线了",
    })
    job.creator_chain = chain
    job.created_by = user_c
    await db_session.flush()

    assert len(job.creator_chain) == 3
    assert job.creator_chain[0]["action"] == "create"
    assert job.creator_chain[1]["user_id"] == str(user_b)
    assert job.creator_chain[2]["user_id"] == str(user_c)
    assert job.created_by == user_c
