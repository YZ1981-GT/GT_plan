"""OO→HTML apply 串行锁的加锁与解锁必须在同一条连接上（spec writeback-followup-issue-closure R3.1）。

原实现在**会话**上执行 `pg_advisory_lock` / `pg_advisory_unlock`。临界区里会 commit，会话每次 commit
都把连接还给池 ⇒ 解锁落到另一条连接上（返回 false），锁留在池里那条空闲连接上，同 room 的下一个
apply 永久等待。判据在真实 PostgreSQL 上跑（advisory lock 是数据库行为，SQLite 没有），且先证明
场景真的换了连接（会话前后拿到不同的后端进程），否则判据是空转：

1. 持锁期间另一条连接 `pg_try_advisory_lock` 拿不到；临界区内会话 commit、换连接不影响持锁；
2. 解锁后 `pg_locks` 里没有这把锁，另一条连接能立即拿到；
3. 同一仓储内重入（锁两次、解两次）只在最后一次解锁时释放。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from app.core.config import settings

_HELD_SQL = sa.text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
    "AND classid = CAST(:ns AS oid) AND objid = CAST(hashtext(:key) AS oid) AND objsubid = 2"
)


async def _held(engine, ns: int, key: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(_HELD_SQL, {"ns": ns, "key": key})).scalar_one())


async def _try_lock(engine, ns: int, key: str) -> bool:
    async with engine.connect() as conn:
        got = bool((await conn.execute(
            sa.text("SELECT pg_try_advisory_lock(:ns, hashtext(:key))"), {"ns": ns, "key": key}
        )).scalar_one())
        if got:
            await conn.execute(sa.text("SELECT pg_advisory_unlock(:ns, hashtext(:key))"), {"ns": ns, "key": key})
        return got


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services.workpaper_sync import repository as R

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    # 生产同款的连接池；先把 3 条连接放进池，会话每次 commit 后才会轮到别的连接
    engine = create_async_engine(settings.DATABASE_URL, pool_size=3, max_overflow=2, connect_args=ssl_off)
    out: dict[str, Any] = {}
    try:
        warm = [await engine.connect() for _ in range(3)]
        for c in warm:
            await c.close()
        ns = R._ADVISORY_NAMESPACE
        room = uuid.uuid4()
        key = f"oo_apply:{room}"
        async with AsyncSession(engine) as session:
            repo = R.WorkpaperSyncRepository(session)
            await repo.lock_room_oo_apply(room)
            out["held_after_lock"] = await _held(engine, ns, key)
            async with engine.connect() as probe:
                out["holder_state"] = (await probe.execute(sa.text(
                    "SELECT a.state FROM pg_stat_activity a JOIN pg_locks l ON l.pid = a.pid "
                    "WHERE l.locktype = 'advisory' AND l.granted AND l.classid = CAST(:ns AS oid) "
                    "AND l.objid = CAST(hashtext(:key) AS oid) AND l.objsubid = 2"
                ), {"ns": ns, "key": key})).scalar_one_or_none()
            pids = []
            for _ in range(4):
                pids.append(int((await session.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()))
                await session.commit()
            out["session_pids"] = pids
            out["other_can_lock_while_held"] = await _try_lock(engine, ns, key)
            await repo.unlock_room_oo_apply(room)
            out["held_after_unlock"] = await _held(engine, ns, key)
            out["other_can_lock_after"] = await _try_lock(engine, ns, key)

            again = uuid.uuid4()
            akey = f"oo_apply:{again}"
            await repo.lock_room_oo_apply(again)
            await repo.lock_room_oo_apply(again)
            await repo.unlock_room_oo_apply(again)
            out["reentrant_held_after_first_unlock"] = await _held(engine, ns, akey)
            await repo.unlock_room_oo_apply(again)
            out["reentrant_held_after_second_unlock"] = await _held(engine, ns, akey)
            out["leftover_lock_connections"] = len(repo._oo_apply_locks)
        out["pool_checked_out_at_end"] = engine.pool.checkedout()
    finally:
        await engine.dispose()
    return out


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    if not settings.DATABASE_URL.startswith("postgresql"):
        pytest.fail("advisory lock 是数据库行为，判据必须在 PostgreSQL 上跑（不 skip）")
    return asyncio.run(_collect())


def test_scenario_really_switches_connections(facts):
    assert len(set(facts["session_pids"])) >= 2, (
        f"会话 commit 后没有换连接（{facts['session_pids']}），判据是空转"
    )


def test_lock_is_held_across_session_commits(facts):
    assert facts["held_after_lock"] == 1
    assert facts["other_can_lock_while_held"] is False
    assert facts["holder_state"] == "idle", "持锁连接不得挂着未结束的事务（idle in transaction）"


def test_lock_connections_go_back_to_the_pool(facts):
    assert facts["pool_checked_out_at_end"] == 0, "持锁的专用连接解锁后没有归还"


def test_unlock_releases_on_the_locking_connection(facts):
    assert facts["held_after_unlock"] == 0, "锁留在了池里的空闲连接上"
    assert facts["other_can_lock_after"] is True


def test_reentrant_lock_releases_only_at_the_last_unlock(facts):
    assert facts["reentrant_held_after_first_unlock"] == 1
    assert facts["reentrant_held_after_second_unlock"] == 0
    assert facts["leftover_lock_connections"] == 0
