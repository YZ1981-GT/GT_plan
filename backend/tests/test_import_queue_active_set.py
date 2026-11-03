"""导入锁 Redis 活跃集合：残留成员清理 + release_lock 清 Redis（spec mapping-code-collision-and-fetch-by-mapping 第二批）。

真库现象：全部导入流程调同步 ``release_lock``（原来只清内存），活跃集合 ``import_lock:active_set`` 没有过期时间、
成员永久累积，满 3 个后所有导入报「系统繁忙」。Redis 用测试基座的 ``_isolated_import_queue_redis``（每例独享 fakeredis）。
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

import app.models.audit_platform_models  # noqa: E402, F401
import app.models.core  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.models.audit_platform_models import ImportBatch, ImportStatus  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.services import import_queue_service as iq  # noqa: E402
from app.services.import_queue_service import ImportQueueService  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _acquire(db_session, project_id):
    return await ImportQueueService.acquire_lock(
        project_id, "tester", db_session, source_type="smart_import", file_name="ledger.csv", year=2024,
    )


@pytest.mark.asyncio
async def test_prunes_stale_active_set_members(db_session: AsyncSession, _isolated_import_queue_redis):
    """活跃集合满额但成员是残留（无锁键、无进行中批次）⇒ 清掉后放行；有锁键 / 有进行中批次的保留。"""
    redis = _isolated_import_queue_redis
    stale1, stale2, live_lock, live_batch = (str(uuid.uuid4()) for _ in range(4))
    await redis.sadd(iq._REDIS_ACTIVE_SET_KEY, stale1, stale2, live_lock, live_batch)
    await redis.set(f"{iq._REDIS_LOCK_PREFIX}{live_lock}", "1", ex=60)
    db_session.add(ImportBatch(
        project_id=uuid.UUID(live_batch), year=2024, source_type="smart_import", file_name="x.csv",
        data_type=iq.IMPORT_JOB_DATA_TYPE, status=ImportStatus.processing,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None), validation_summary={"job": True},
    ))
    await db_session.commit()

    new_pid = uuid.uuid4()
    ok, msg, _ = await _acquire(db_session, new_pid)
    assert ok is True, msg
    assert await redis.smembers(iq._REDIS_ACTIVE_SET_KEY) == {live_lock, live_batch, str(new_pid)}


@pytest.mark.asyncio
async def test_still_busy_when_members_are_live(db_session: AsyncSession, _isolated_import_queue_redis):
    redis = _isolated_import_queue_redis
    members = [str(uuid.uuid4()) for _ in range(3)]
    await redis.sadd(iq._REDIS_ACTIVE_SET_KEY, *members)
    for m in members:
        await redis.set(f"{iq._REDIS_LOCK_PREFIX}{m}", "1", ex=60)
    ok, msg, batch_id = await _acquire(db_session, uuid.uuid4())
    assert ok is False and "系统繁忙" in msg and batch_id is None
    assert await redis.smembers(iq._REDIS_ACTIVE_SET_KEY) == set(members)


@pytest.mark.asyncio
async def test_own_leftover_member_does_not_block_reimport(db_session: AsyncSession, _isolated_import_queue_redis):
    """本项目上次导入留下的成员（释放没走到 Redis）：重新导入时算残留，不占名额。"""
    redis = _isolated_import_queue_redis
    pid = uuid.uuid4()
    others = [str(uuid.uuid4()) for _ in range(2)]
    await redis.sadd(iq._REDIS_ACTIVE_SET_KEY, str(pid), *others)
    for m in others:
        await redis.set(f"{iq._REDIS_LOCK_PREFIX}{m}", "1", ex=60)
    ok, msg, _ = await _acquire(db_session, pid)
    assert ok is True, msg
    assert await redis.smembers(iq._REDIS_ACTIVE_SET_KEY) == {str(pid), *others}


@pytest.mark.asyncio
async def test_release_lock_clears_redis_lock_and_active_set(db_session: AsyncSession, _isolated_import_queue_redis):
    """全部导入流程走同步 release_lock：Redis 锁键与活跃集合成员也要清掉（原来只清内存）。"""
    redis = _isolated_import_queue_redis
    pid = uuid.uuid4()
    ok, msg, _ = await _acquire(db_session, pid)
    assert ok is True, msg
    assert await redis.sismember(iq._REDIS_ACTIVE_SET_KEY, str(pid))
    assert await redis.exists(f"{iq._REDIS_LOCK_PREFIX}{pid}")

    ImportQueueService.release_lock(pid)
    await asyncio.gather(*list(iq._pending_redis_releases))
    assert not await redis.sismember(iq._REDIS_ACTIVE_SET_KEY, str(pid))
    assert not await redis.exists(f"{iq._REDIS_LOCK_PREFIX}{pid}")
    assert str(pid) not in iq._import_locks
