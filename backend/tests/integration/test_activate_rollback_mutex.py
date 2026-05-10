"""F23 / Sprint 5.15: activate 与 rollback 互斥集成测试。

背景（design §D5 / requirements F23）：
- `DatasetService.rollback` 已接入 `ImportQueueService.try_acquire_action_lock`
  与 activate 共享同一项目级锁；同项目内 activate / rollback / import 三者互斥。
- 锁是基于内存字典 `_import_locks` 的单进程互斥（跨进程/多 worker 靠 DB
  唯一索引 —— 见 `acquire_lock`）。

本文件覆盖 4 条场景：
1. 已占锁时再次尝试同一 action 应失败；
2. 正确释放后可重新获取；
3. `get_lock_info` 返回 action + holder_user_id（F21 锁透明）；
4. 无锁时 `get_lock_info` 返回 None。

Fixture 参考 `test_dataset_rollback_view_refactor.py`（SQLite in-memory）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.services.import_queue_service import (
    ImportQueueService,
    _import_locks,
)


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


@pytest.fixture(autouse=True)
def _clear_locks():
    """每个测试前后都清空内存锁字典，确保测试隔离。"""
    _import_locks.clear()
    yield
    _import_locks.clear()


# ---------------------------------------------------------------------------
# 场景 1：同项目两次 rollback 互斥
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rollback_mutex_prevents_concurrent_rollback(db_session: AsyncSession):
    """F23: 同项目 rollback 进行中时，第二次尝试应被拒绝。"""
    project_id = uuid.uuid4()

    # 第一次获取成功
    acquired = ImportQueueService.try_acquire_action_lock(
        project_id, action="rollback", user_id=str(uuid.uuid4())
    )
    assert acquired is True

    # 第二次应失败（已被占用）
    second = ImportQueueService.try_acquire_action_lock(
        project_id, action="rollback", user_id=str(uuid.uuid4())
    )
    assert second is False

    # 释放后即可恢复
    ImportQueueService.release_action_lock(project_id)


# ---------------------------------------------------------------------------
# 场景 2：activate 与 rollback 共享锁 —— 一方持锁时另一方也被拒绝
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_activate_and_rollback_share_same_lock(db_session: AsyncSession):
    """F23 核心：activate 进行中时 rollback 应被拒绝，反之亦然。"""
    project_id = uuid.uuid4()

    # activate 先拿锁
    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="activate")
        is True
    )

    # rollback 应被拒
    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="rollback")
        is False
    )

    # 反向：释放 activate，rollback 再持锁时 activate 应被拒
    ImportQueueService.release_action_lock(project_id)
    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="rollback")
        is True
    )
    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="activate")
        is False
    )

    ImportQueueService.release_action_lock(project_id)


# ---------------------------------------------------------------------------
# 场景 3：释放后可重新获取（锁状态完整恢复）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_release_allows_subsequent_acquire(db_session: AsyncSession):
    """释放动作锁后，后续 acquire 应成功。"""
    project_id = uuid.uuid4()

    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="rollback")
        is True
    )
    ImportQueueService.release_action_lock(project_id)

    assert (
        ImportQueueService.try_acquire_action_lock(project_id, action="activate")
        is True
    )
    ImportQueueService.release_action_lock(project_id)


# ---------------------------------------------------------------------------
# 场景 4（F21）：get_lock_info 返回 action + holder 信息
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_lock_info_returns_action_and_holder(db_session: AsyncSession):
    """F21: get_lock_info 必须返回 action=rollback + holder_user_id。

    holder_name 在 User 表无对应记录时可为 None，不作强断言。
    """
    project_id = uuid.uuid4()
    user_id = uuid.uuid4()

    ImportQueueService.try_acquire_action_lock(
        project_id, action="rollback", user_id=str(user_id)
    )

    info = await ImportQueueService.get_lock_info(project_id, db_session)
    assert info is not None
    assert info["has_lock"] is True
    assert info["action"] == "rollback"
    assert info["holder_user_id"] == str(user_id)
    # job_id 对 action_lock 场景应为 None（没有 ImportJob 关联）
    assert info["job_id"] is None
    # 基本结构字段必须存在
    for key in (
        "holder_name",
        "current_phase",
        "current_phase_cn",
        "progress_pct",
        "acquired_at",
        "progress_message",
    ):
        assert key in info, f"LockInfo 缺少字段 {key}"

    ImportQueueService.release_action_lock(project_id)


# ---------------------------------------------------------------------------
# 场景 5（F21）：无锁时 get_lock_info 返回 None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_lock_info_none_when_no_lock(db_session: AsyncSession):
    """F21: 无活跃 job 且无 action_lock 时应返回 None。"""
    project_id = uuid.uuid4()
    info = await ImportQueueService.get_lock_info(project_id, db_session)
    assert info is None


# ---------------------------------------------------------------------------
# 场景 6（F23）：不同项目之间锁独立
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_locks_are_scoped_per_project(db_session: AsyncSession):
    """F23: 不同项目的锁互不影响（只在同 project_id 内互斥）。"""
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()

    assert ImportQueueService.try_acquire_action_lock(project_a, action="rollback")
    # 项目 B 的 rollback 应不受项目 A 的影响
    assert ImportQueueService.try_acquire_action_lock(project_b, action="rollback")

    ImportQueueService.release_action_lock(project_a)
    ImportQueueService.release_action_lock(project_b)
