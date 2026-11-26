"""Outbox 重放不得持着事务行锁去 await handler 的独立会话（真 PG 守卫）。

🔴 缺陷现场（2026-11-15 共享库实测）
-----------------------------------
``import_event_outbox`` 里两条 ``pending`` 行（``attempt_count=0``）从批准起 17 分钟
未被消费，而 ``outbox_replay_worker`` 心跳一直正常（健康页 healthy）。只有
``pg_stat_activity`` 能看到真相：

    pid A | idle in transaction | RELEASE SAVEPOINT sa_savepoint_1   ← replay 会话
    pid B | active   | Lock/transactionid | SELECT projects.id, ...
    pid C | active   | Lock/tuple         | SELECT projects.id, ...

``pg_blocking_pids`` 显示 B 等 A、C 等 B，而 A 在等 handler 返回 ⇒ 环形等待；
清掉三个会话后 55 秒内以新 PID 复现。

结构性成因
----------
``replay_pending`` 用 ``with_for_update(skip_locked=True)`` 锁 outbox 行，随后**在同一个
未提交事务里**同步 ``await`` handler；生产 handler 一律自开 session
（``async_session_factory``）。父事务未提交时，子会话要更新的任何父事务已锁住的
行/索引都会被阻塞，而父事务又在等子会话返回 —— 这是「在开放事务里做外部 IO」的
经典形态，即使当前 handler 恰好不撞行，也随时会被任何一个新 handler 触发。

修复
----
唯一派发口 ``_deliver`` 在真正 await handler 之前先 ``commit()``
（``_release_locks_before_deliver``），把行锁全部释放。认领行与 ``attempt_count``
由这次提交保留，重放幂等语义不变。

本守卫为什么这样写（血泪）
--------------------------
第一版想「复现死锁」：造 2 条 pending + 生产 handler，断言 replay 在 30s 内返回。
结果**变异掉修复后仍然绿**（2026-11-15 实测 0.1s 返回）——单进程顺序执行时父事务的
``FOR UPDATE`` 并不会被自己同步 await 的子会话阻塞，只有真正并发/特定行冲突才炸。
那种断言等于没有断言。

改成直接钉住**不变量**：handler 被调用的那一刻，另一个连接对该 outbox 行做
``SELECT ... FOR UPDATE NOWAIT`` 必须**立刻成功**。
  · 修复在 ⇒ replay 已提交、行锁已释放 ⇒ 成功；
  · 修复被变异掉 ⇒ replay 仍持着该行的 ``FOR UPDATE`` ⇒ 立刻 ``lock_not_available``。
这既是确定性的，也精确对应缺陷的因果（不是"看起来没卡住"）。

只在专用验收库跑（``GT_ADJ_ACCEPT_DB_URL``），未设置即 skip。
"""
from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

ACCEPT_URL_ENV = "GT_ADJ_ACCEPT_DB_URL"

pytestmark = pytest.mark.pg_only


def _accept_url() -> str:
    url = (os.environ.get(ACCEPT_URL_ENV) or "").strip()
    if not url:
        pytest.skip(
            f"需要专用验收库：设置 {ACCEPT_URL_ENV}"
            "（见 backend/scripts/e2e/create_adjustment_accept_db.py）"
        )
    if not url.startswith("postgresql"):
        pytest.skip(f"{ACCEPT_URL_ENV} 必须是 PostgreSQL 连接串")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture(scope="module", autouse=True)
def _models_loaded():
    import app.models as models_pkg

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{mod.name}")


@pytest_asyncio.fixture
async def observer_engine():
    """独立的观察连接（模拟 handler 的独立 session），用于 NOWAIT 探测行锁。"""
    engine = create_async_engine(_accept_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def world(observer_engine):
    """一个【测试】项目 + 一个 actor；用完按项目粒度清理。"""
    from app.models.base import UserRole
    from app.models.core import Project, User

    owner = async_sessionmaker(observer_engine.kw["bind"], class_=AsyncSession,
                               expire_on_commit=False) if False else observer_engine
    project_id, actor_id = uuid.uuid4(), uuid.uuid4()
    async with owner() as db:
        db.add(User(
            id=actor_id, username=f"t_lc_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@t.local", hashed_password="x",
            role=UserRole.admin, is_active=True,
        ))
        await db.flush()
        db.add(Project(
            id=project_id,
            name=f"【测试】锁convoy {uuid.uuid4().hex[:8]}",
            client_name="【测试】锁convoy",
            status="planning",
            created_by=actor_id, company_code="001",
        ))
        await db.commit()
    try:
        yield {"project_id": project_id, "actor_id": actor_id, "factory": owner}
    finally:
        async with owner() as db:
            for sql in (
                "delete from event_outbox_dlq where project_id = :p",
                "delete from import_event_consumptions where project_id = :p",
                "delete from import_event_outbox where project_id = :p",
                "delete from event_cascade_log where project_id = :p",
                "delete from tb_change_history where project_id = :p",
                "delete from logs where user_id = :u",
                "delete from projects where id = :p",
                "delete from users where id = :u",
            ):
                try:
                    await db.execute(sa.text(sql), {"p": project_id, "u": actor_id})
                    await db.commit()
                except Exception:  # noqa: BLE001 - 表可能不存在；回滚继续
                    await db.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _restore_event_bus_handlers():
    from app.services.event_bus import event_bus

    snapshot = {et: list(hs) for et, hs in event_bus._handlers.items()}
    try:
        yield
    finally:
        event_bus._handlers.clear()
        for et, hs in snapshot.items():
            event_bus._handlers[et] = list(hs)
        try:
            import app.services.event_handlers as pkg

            registry = getattr(pkg, "_REGISTERED", None)
            if registry is not None:
                registry.clear()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# 核心不变量
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handler_runs_after_replay_releases_the_outbox_row_lock(
    world, observer_engine,
):
    """handler 被调用时，replay 事务必须已经释放 outbox 行锁。

    判据 = 另一个连接对该行 ``SELECT ... FOR UPDATE NOWAIT`` 立刻成功。
    """
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.event_bus import event_bus
    from app.services.import_event_outbox_service import ImportEventOutboxService
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    project_id = world["project_id"]
    factory = world["factory"]

    async with factory() as db:
        event = EventPayload(
            event_type=EventType.ADJUSTMENT_APPROVED,
            project_id=project_id, year=2025,
            account_codes=["1122"], entry_group_id=uuid.uuid4(),
            extra={"origin": "manual", "operator_id": str(world["actor_id"])},
        )
        await DurableEventOutboxService.enqueue_event(db, event)
        await db.commit()

    observations: list[dict[str, object]] = []

    async def probe(payload: EventPayload) -> None:
        """在 handler 的独立 session 里探测 outbox 行是否仍被 replay 事务锁住。"""
        event_id = (payload.extra or {}).get("__event_id")
        async with observer_engine() as probe_db:
            try:
                await probe_db.execute(sa.text(
                    "select id from import_event_outbox "
                    "where id = :i for update nowait"
                ), {"i": event_id})
                observations.append({"lock_released": True})
                await probe_db.rollback()
            except Exception as exc:  # noqa: BLE001
                observations.append({
                    "lock_released": False,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                })
                await probe_db.rollback()

    # 只留探针：断言的目标是「replay 派发前有没有释放锁」，不该被生产 handler 的
    # 长下游（ReportEngine / DeliverableStale）拖慢或干扰。
    event_bus._handlers[EventType.ADJUSTMENT_APPROVED] = [probe]

    async with factory() as db:
        report = await asyncio.wait_for(
            ImportEventOutboxService.replay_pending(db, limit=10, max_attempts=3),
            timeout=30,
        )
        await db.commit()

    assert report["published_count"] == 1, report
    assert observations, "探针 handler 没有被调用（replay 根本没派发）"
    bad = [o for o in observations if not o.get("lock_released")]
    assert not bad, (
        "handler 运行时 outbox 行仍被 replay 事务锁住 ⇒ replay 在开放事务里 await "
        f"handler 的独立会话（派发前必须先 commit 释放锁）：{bad}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["replay_pending", "publish_one"])
async def test_handler_runs_after_fanout_claim_is_committed(world, observer_engine, path):
    """handler 被调用时，闸门认领行（及其对 projects 的外键锁）也必须已提交。

    🔴 2026-11-26 formula-e2e 实测：上一条守卫只看 outbox 行锁，而 ``_deliver`` 提交之后
    ``begin_fanout`` 又在本会话插 ``import_event_consumptions``（``project_id`` 外键 ⇒ 对
    projects 行加 KEY SHARE，且开了新的未提交事务），随即 await handler。handler 的独立
    会话一 ``SELECT projects ... FOR UPDATE`` 就等这个 txid ⇒ 同形自锁死锁，pending/resolve
    之后每个请求都卡 60 秒。判据：探针对本项目行 ``FOR UPDATE NOWAIT`` 必须立刻成功。
    """
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.event_bus import event_bus
    from app.services.import_event_outbox_service import ImportEventOutboxService
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    project_id = world["project_id"]
    factory = world["factory"]

    async with factory() as db:
        event = EventPayload(
            event_type=EventType.ADJUSTMENT_APPROVED,
            project_id=project_id, year=2025,
            account_codes=["1122"], entry_group_id=uuid.uuid4(),
            extra={"origin": "manual", "operator_id": str(world["actor_id"])},
        )
        publication = await DurableEventOutboxService.enqueue_event(db, event)
        await db.commit()

    observations: list[dict[str, object]] = []

    async def probe(payload: EventPayload) -> None:
        async with observer_engine() as probe_db:
            try:
                await probe_db.execute(sa.text(
                    "select id from projects where id = :p for update nowait"
                ), {"p": project_id})
                observations.append({"lock_released": True})
            except Exception as exc:  # noqa: BLE001
                observations.append({"lock_released": False, "error": type(exc).__name__,
                                     "detail": str(exc)[:200]})
            finally:
                await probe_db.rollback()

    event_bus._handlers[EventType.ADJUSTMENT_APPROVED] = [probe]

    async with factory() as db:
        if path == "replay_pending":
            await asyncio.wait_for(
                ImportEventOutboxService.replay_pending(db, limit=10, max_attempts=3), timeout=30)
        else:
            await asyncio.wait_for(
                ImportEventOutboxService.publish_one(db, publication.outbox_id), timeout=30)
        await db.commit()

    assert observations, "探针 handler 没有被调用"
    bad = [o for o in observations if not o.get("lock_released")]
    assert not bad, (
        "handler 运行时本会话仍持有 projects 行的外键锁 ⇒ begin_fanout 的认领行未提交就派发："
        f"{bad}"
    )


@pytest.mark.asyncio
async def test_replay_still_dedups_after_lock_release(world, observer_engine):
    """释放锁不能把幂等闸门一起丢掉：同一事件重放第二遍必须被去重。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.event_bus import event_bus
    from app.services.import_event_outbox_service import ImportEventOutboxService
    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    project_id = world["project_id"]
    factory = world["factory"]

    async with factory() as db:
        event = EventPayload(
            event_type=EventType.ADJUSTMENT_APPROVED,
            project_id=project_id, year=2025,
            account_codes=["1122"], entry_group_id=uuid.uuid4(),
            extra={"origin": "manual", "operator_id": str(world["actor_id"])},
        )
        publication = await DurableEventOutboxService.enqueue_event(db, event)
        await db.commit()

    calls: list[str] = []

    async def probe(payload: EventPayload) -> None:
        calls.append((payload.extra or {}).get("__event_id", "?"))

    event_bus._handlers[EventType.ADJUSTMENT_APPROVED] = [probe]

    async with factory() as db:
        first = await asyncio.wait_for(
            ImportEventOutboxService.replay_pending(db, limit=10, max_attempts=3), timeout=30,
        )
        await db.commit()
    assert first["published_count"] == 1, first
    assert len(calls) == 1, calls

    # 模拟「发布成功但状态没落库」的补偿重放。
    async with factory() as db:
        await db.execute(sa.text(
            "update import_event_outbox set status = 'pending', published_at = null "
            "where id = :i"
        ), {"i": publication.outbox_id})
        await db.commit()

    async with factory() as db:
        second = await asyncio.wait_for(
            ImportEventOutboxService.replay_pending(db, limit=10, max_attempts=3), timeout=30,
        )
        await db.commit()

    # 认领行必须还在（修复若误用 rollback 释放锁，认领行会被回滚掉、副作用重放）。
    assert second["deduplicated_fanout_count"] == 1, second
    assert len(calls) == 1, f"副作用被重复派发：{calls}"
