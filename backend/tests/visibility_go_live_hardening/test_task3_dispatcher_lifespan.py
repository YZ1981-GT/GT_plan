# Feature: visibility-isolation-go-live-hardening — Task 3 挂载 InvalidationDispatcher 到 app.main lifespan（R2）
"""Task 3 / Requirements 2.1–2.10（组件 H2 DispatcherLifecycle / C15 Cache/Rate/Perf）。

证明五件事，**真实 FastAPI app + 真实 PostgreSQL（audit_platform）+ fakeredis / Redis-down 模拟**，
绝不假绿、绝不改 ``epoch_cache`` 语义：

  A. **subscriber 挂载**（Req 2.1）：``app.main._start_workers`` 在 lifespan 启动时创建
     invalidation dispatcher task（subscriber + publisher）；开关关闭时 worker 优雅退出（回退路径）。

  B. **Fast_Path 收敛 ≤1s**（Req 2.2/2.3/2.4）：publisher 读**已提交** invalidation outbox 行 →
     fan-out 到项目 Redis channel（fakeredis）→ subscriber psubscribe 收到 → 立即
     ``PersistentEpochCache.invalidate(project)`` → 本地 epoch 新鲜度与缓存条目在 ≤1s 内清空。

  C. **Redis-down 启动 + DB 安全网**（Req 2.5/2.6/2.7）：Redis 启动时不可用（``get_redis``→None）→
     worker 不崩溃、不阻塞应用启动、进入退避重连；撤权（epoch 递增）后即便无 Redis，
     ``PersistentEpochCache`` 的 ≤1s DB epoch 安全网在 ≤1s 内拒绝旧 grant（no stale-allow）。

  D. **重连 resubscribe**（Req 2.9）：subscriber 运行期断连（``run_invalidation_subscriber`` 返回）→
     重连循环再次拉起并 resubscribe（调用计数 ≥2）。

  E. **优雅停止**（Req 2.8）：``stop_event`` 置位 → ``run`` 优雅退出，无异常。

不改父 spec 组件语义：仅复用 ``run_invalidation_subscriber`` / ``InvalidationDispatcher`` /
``PersistentEpochCache``，在其外层加挂载/退避重连/优雅停止编排。每 PG 用例事务隔离回滚。
"""
from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.wp_visibility_models import WpVisibilityInvalidationOutbox
from app.services.wp_visibility.epoch_cache import (
    PersistentEpochCache,
    invalidation_channel,
)
from app.services.wp_visibility.invalidation_dispatcher import InvalidationDispatcher
from app.workers import invalidation_dispatcher_worker as idw

from tests.procedure_delegation_visibility._factories import (
    IS_PG,
    mk_project,
    mk_project_user,
    mk_user,
    mk_working_paper,
    mk_wp_index,
)

pytestmark = pytest.mark.asyncio

_TIMEOUT = 5.0


class _Clock:
    """可控单调假时钟：精确验证 ≤1s DB epoch 核对窗口。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class _PgCtx:
    """真实 PostgreSQL 事务隔离上下文（用例结束整体回滚，绝不污染 dev 库）。"""

    def __init__(self) -> None:
        self.engine = None
        self.conn = None
        self.trans = None
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self.engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True)
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        self.session = AsyncSession(bind=self.conn, join_transaction_mode="create_savepoint")
        return self.session

    async def __aexit__(self, *exc) -> None:
        if self.session is not None:
            await self.session.close()
        if self.trans is not None:
            await self.trans.rollback()
        if self.conn is not None:
            await self.conn.close()
        if self.engine is not None:
            await self.engine.dispose()


async def _lead_scenario(s, *, scope="D", cycle="D"):
    """lead 底稿 + project user（授权真源）。policy epoch 行按需另插。"""
    proj = await mk_project(s)
    user = await mk_user(s)
    wi = await mk_wp_index(s, proj.id, wp_code="D2-1", audit_cycle=cycle)
    wp = await mk_working_paper(s, proj.id, wi.id)
    wp.assigned_to = user.id
    await mk_project_user(s, proj.id, user.id, scope_cycles=scope)
    await s.flush()
    return proj, user, wi, wp


# ===========================================================================
# A. subscriber 挂载到 lifespan（Req 2.1）+ 开关回退
# ===========================================================================
class TestDispatcherMounted:
    async def test_start_workers_creates_dispatcher_task(self):
        """_start_workers 创建 invalidation dispatcher task（挂载到 lifespan，Req 2.1）。"""
        from app.main import _start_workers

        stop_event = asyncio.Event()
        stop_event.set()  # 立即置位，避免真实 worker 副作用
        tasks = _start_workers(stop_event)
        try:
            files = [
                (t.get_coro().cr_code.co_filename if hasattr(t.get_coro(), "cr_code") else "")
                for t in tasks
            ]
            assert any("invalidation_dispatcher_worker" in f for f in files), (
                "lifespan _start_workers 未挂载 invalidation dispatcher"
            )
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_flag_off_worker_exits(self, monkeypatch):
        """VISIBILITY_INVALIDATION_DISPATCHER_ENABLED=False → worker 直接退出（回退路径）。"""
        monkeypatch.setattr(app_settings, "VISIBILITY_INVALIDATION_DISPATCHER_ENABLED", False)
        stop_event = asyncio.Event()
        # 不置位 stop_event：若未因开关退出会挂起 → wait_for 超时暴露。
        await asyncio.wait_for(idw.run(stop_event), timeout=_TIMEOUT)  # 应立即返回

    async def test_default_flag_is_true(self):
        """默认挂载（开关默认 True）。"""
        from app.core.config import Settings

        assert Settings(_env_file=None).VISIBILITY_INVALIDATION_DISPATCHER_ENABLED is True


# ===========================================================================
# B. Fast_Path：publisher(提交后 outbox)→Redis→subscriber invalidate ≤1s（Req 2.2/2.3/2.4）
# ===========================================================================
@pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (invalidation outbox)")
class TestFastPathConvergence:
    async def test_committed_outbox_fanned_out_and_converges(self):
        import fakeredis.aioredis

        fake = fakeredis.aioredis.FakeRedis(decode_responses=False)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        stop = asyncio.Event()
        sub_task = None
        try:
            proj, _user, _wi, _wp = await _lead_scenario(s)
            # 权限事务提交后写入的 outbox 行（这里以 flush 模拟已提交可见行；
            # 真实链路由 DelegationTransaction._bump_epoch 在同事务写、router commit 后可见）。
            s.add(
                WpVisibilityInvalidationOutbox(
                    project_id=proj.id, epoch=2, change_type="delegation",
                    request_id="task3-fastpath", actor_user_id=None,
                    detail={"layer": "row", "action": "revoke"},
                )
            )
            await s.flush()

            # subscriber 用独立 cache（不经 local_cache 直投，纯验证 Redis fan-out 路径）。
            cache = PersistentEpochCache()
            # 预置一条缓存条目 + epoch 新鲜度（模拟已缓存的 grant）。
            cache._epoch_freshness[proj.id] = cache._epoch_freshness.get(proj.id)  # noqa: SLF001
            from app.services.wp_visibility.epoch_cache import _EpochFreshness

            cache._epoch_freshness[proj.id] = _EpochFreshness(1, cache.clock())  # noqa: SLF001
            cache._entries[("u", proj.id, "wi")] = (1, ["lead"])  # noqa: SLF001
            assert cache.cached_epoch_for(proj.id) == 1
            assert cache.entry_count() == 1

            from app.services.wp_visibility.invalidation_dispatcher import (
                run_invalidation_subscriber,
            )

            sub_task = asyncio.create_task(
                run_invalidation_subscriber(cache, redis=fake, stop_event=stop)
            )
            # 等 psubscribe 就绪（Redis-down 场景不会到这，这里 fakeredis 一定就绪）。
            await _await_subscribed(fake)

            # publisher：不带 local_cache → 仅经 Redis fan-out（隔离验证快路径）。
            dispatcher = InvalidationDispatcher(local_cache=None)
            t0 = time.monotonic()
            published = await dispatcher.publish_pending(s, fake)
            assert published >= 1, "publisher 未 fan-out 已提交 outbox 行"

            converged = await _wait_until(
                lambda: cache.cached_epoch_for(proj.id) is None and cache.entry_count() == 0,
                deadline=1.0,
            )
            elapsed = time.monotonic() - t0
            assert converged, "Fast_Path 未在 ≤1s 内使缓存收敛"
            assert elapsed <= 1.0
        finally:
            stop.set()
            if sub_task is not None:
                await asyncio.gather(sub_task, return_exceptions=True)
            await ctx.__aexit__()
            await fake.aclose()

    async def test_handle_message_invalidates_project(self):
        """channel 名解析 → invalidate 对应 project（快路径核心，纯函数）。"""
        from uuid import uuid4

        from app.services.wp_visibility.invalidation_dispatcher import (
            handle_invalidation_message,
        )

        cache = PersistentEpochCache()
        from app.services.wp_visibility.epoch_cache import _EpochFreshness

        pid = uuid4()
        cache._epoch_freshness[pid] = _EpochFreshness(3, cache.clock())  # noqa: SLF001
        cache._entries[("u", pid, "wi")] = (3, ["lead"])  # noqa: SLF001
        assert handle_invalidation_message(cache, invalidation_channel(pid)) is True
        assert cache.cached_epoch_for(pid) is None
        assert cache.entry_count() == 0
        # 非本前缀 channel → 不处理
        assert handle_invalidation_message(cache, "other:channel") is False


# ===========================================================================
# C. Redis-down 启动不阻塞 + DB epoch ≤1s 安全网 fail-closed（Req 2.5/2.6/2.7）
# ===========================================================================
class TestRedisDownStartup:
    async def test_subscriber_redis_down_backoff_no_crash(self, monkeypatch):
        """Redis 启动时不可用（get_redis→None）→ subscriber 退避重连、不崩溃、不阻塞（Req 2.5）。"""
        calls = {"n": 0}

        async def _no_redis():
            calls["n"] += 1
            return None

        stop = asyncio.Event()
        task = asyncio.create_task(
            idw._run_subscriber_with_reconnect(
                stop, cache=PersistentEpochCache(), redis_factory=_no_redis,
                base_backoff=0.02, max_backoff=0.05,
            )
        )
        await asyncio.sleep(0.15)  # 允许多轮退避重连
        assert calls["n"] >= 2, "Redis-down 未进入退避重连循环"
        stop.set()
        await asyncio.wait_for(task, timeout=_TIMEOUT)  # 优雅退出，无异常

    async def test_publisher_redis_down_noop_no_crash(self, monkeypatch):
        """Redis 不可得 → publish_pending 返回 0（no-op 降级），无异常（Req 2.5/2.6）。"""
        # 模拟 Redis 全挂：get_redis 返回 None（本 dev 环境实际有真实 Redis，须显式降级）。
        async def _no_redis():
            return None

        monkeypatch.setattr("app.core.redis.get_redis", _no_redis)
        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            dispatcher = InvalidationDispatcher(local_cache=None)
            # redis=None 且 get_redis 降级返回 None → publish_pending no-op 返回 0（不抛出）。
            published = await dispatcher.publish_pending(s, None)
            assert published == 0
        finally:
            await ctx.__aexit__()

    @pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (persistent policy epoch)")
    async def test_db_epoch_safety_net_denies_within_1s_no_stale_allow(self):
        """无 Redis / dispatcher：撤权(epoch 递增)后 DB epoch ≤1s 安全网拒绝旧 grant，绝不 stale-allow（Req 2.6/2.7）。"""
        import sqlalchemy as sa

        from app.models.wp_visibility_models import WpVisibilityPolicyEpoch

        ctx = _PgCtx()
        s = await ctx.__aenter__()
        try:
            proj, user, wi, _wp = await _lead_scenario(s)
            s.add(WpVisibilityPolicyEpoch(project_id=proj.id, epoch=1))
            await s.flush()

            clock = _Clock()
            cache = PersistentEpochCache(epoch_ttl_seconds=1.0, clock=clock)
            state = {"grants": ["lead"]}

            async def loader():
                return list(state["grants"])

            # 预热：epoch=1 缓存 lead grant
            assert await cache.get_or_load(
                s, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
            ) == ["lead"]

            # 撤权：epoch 递增 + loader 现取空（无 Redis 通知）
            await s.execute(
                sa.update(WpVisibilityPolicyEpoch)
                .where(WpVisibilityPolicyEpoch.project_id == proj.id)
                .values(epoch=2)
            )
            await s.flush()
            state["grants"] = []

            # 窗口内（<1s）：仍命中旧条目（≤1s 收敛上界，允许）
            clock.advance(0.4)
            assert await cache.get_or_load(
                s, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
            ) == ["lead"]

            # 超过 ≤1s 安全网窗口：重读 DB epoch=2 → 旧 epoch=1 条目永不匹配 → 权威现取空（拒绝，不 stale-allow）
            clock.advance(1.0)
            assert await cache.get_or_load(
                s, user_id=user.id, project_id=proj.id, wp_index_id=wi.id, loader=loader
            ) == []
        finally:
            await ctx.__aexit__()


# ===========================================================================
# D. 运行期断连 → 重连并 resubscribe（Req 2.9）
# ===========================================================================
class TestReconnectResubscribe:
    async def test_runtime_disconnect_reconnects(self, monkeypatch):
        """subscriber 运行期返回（断连）→ 重连循环再次拉起 psubscribe（调用计数 ≥2，Req 2.9）。"""
        sub_calls = {"n": 0}

        async def _fake_subscriber(cache, *, redis=None, stop_event=None):
            sub_calls["n"] += 1
            # 第 1 次：模拟运行期断连（立即返回，触发重连）；
            # 第 2 次起：模拟重连成功后置 stop 优雅收尾。
            if sub_calls["n"] >= 2 and stop_event is not None:
                stop_event.set()
            return

        async def _ok_redis():
            return object()  # 非 None → 视为 Redis 可用

        monkeypatch.setattr(idw, "run_invalidation_subscriber", _fake_subscriber)
        stop = asyncio.Event()
        await asyncio.wait_for(
            idw._run_subscriber_with_reconnect(
                stop, cache=PersistentEpochCache(), redis_factory=_ok_redis,
                base_backoff=0.01, max_backoff=0.05,
            ),
            timeout=_TIMEOUT,
        )
        assert sub_calls["n"] >= 2, "运行期断连后未重连 resubscribe"


# ===========================================================================
# E. lifespan 关闭 → 优雅停止（Req 2.8）
# ===========================================================================
class TestGracefulShutdown:
    async def test_run_stops_cleanly_on_stop_event(self, monkeypatch):
        """stop_event 置位 → run（subscriber+publisher）优雅退出，无异常（Req 2.8）。"""
        async def _no_redis():
            return None  # 无 Redis：subscriber 退避、publisher no-op

        monkeypatch.setattr("app.core.redis.get_redis", _no_redis)

        # publisher 用不触真实 DB 的 session_factory 降级（本用例只验证优雅停止）。
        async def _run(stop_event):
            await asyncio.gather(
                idw._run_subscriber_with_reconnect(
                    stop_event, cache=PersistentEpochCache(),
                    redis_factory=_no_redis, base_backoff=0.02, max_backoff=0.05,
                ),
                idw._run_publisher_loop(
                    stop_event, dispatcher=InvalidationDispatcher(local_cache=None),
                    session_factory=_NullSession, interval=0.02,
                ),
            )

        stop = asyncio.Event()
        task = asyncio.create_task(_run(stop))
        await asyncio.sleep(0.1)
        assert not task.done()  # 仍在运行（未因异常退出）
        stop.set()
        await asyncio.wait_for(task, timeout=_TIMEOUT)  # 优雅停止
        assert task.exception() is None

    async def test_run_cancel_propagates_cleanly(self):
        """task.cancel() → CancelledError 正常传播（lifespan 关闭 cancel 语义，Req 2.8）。"""
        async def _no_redis():
            return None

        stop = asyncio.Event()
        task = asyncio.create_task(
            idw._run_subscriber_with_reconnect(
                stop, cache=PersistentEpochCache(), redis_factory=_no_redis,
                base_backoff=0.05, max_backoff=0.1,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ===========================================================================
# helpers
# ===========================================================================
class _NullSession:
    """降级 session_factory：async ctx 管理器返回 None（publisher no-op 降级用）。"""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


async def _await_subscribed(fake, deadline: float = 2.0) -> None:
    """等待 fakeredis 的 psubscribe 就绪（否则 fixed sleep 兜底）。"""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        try:
            if await fake.pubsub_numpat() >= 1:
                return
        except Exception:  # noqa: BLE001 — 不支持则退化为固定等待
            await asyncio.sleep(0.2)
            return
        await asyncio.sleep(0.01)


async def _wait_until(predicate, *, deadline: float = 1.0) -> bool:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()
