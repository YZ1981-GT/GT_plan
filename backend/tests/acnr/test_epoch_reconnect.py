"""集成测试: Pub-sub 断连后 epoch 轮询修复 [P16]

**Validates: Requirements 14.1, 14.2, 14.3, 14.4**

Property 16: Pub-sub 断连后 epoch 轮询修复
- 模拟 pub-sub 断开
- 远程 INCR epoch（模拟其他 worker 的写入）
- 60s 内 poll 检测到不一致 → 清除本地缓存

使用 fakeredis + monkeypatch 模拟断连场景。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import fakeredis.aioredis as fakeredis_aio

from app.services.acnr.cache_epoch import (
    EPOCH_KEY_PREFIX,
    EPOCH_POLL_INTERVAL,
    INVALIDATE_CHANNEL_PREFIX,
    RECONNECT_BACKOFF_SCHEDULE,
    _clear_all_local_caches,
    _epoch_poll_task,
    _local_epoch_store,
    _reconnect_loop,
    get_epoch,
    get_redis_client,
    increment_epoch,
    register_local_cache_clear,
    set_local_epoch,
    set_redis_client,
    start_epoch_subscriber,
    stop_epoch_subscriber,
    _local_cache_clear_callbacks,
    _record_fallback_metric,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_module_state():
    """每个测试前重置模块级状态。"""
    _local_epoch_store.clear()
    _local_cache_clear_callbacks.clear()
    set_redis_client(None)
    yield
    _local_epoch_store.clear()
    _local_cache_clear_callbacks.clear()
    set_redis_client(None)


# ─── Test: 轮询检测到不一致后清除缓存 [Req-14.3] ─────────────────────────────


@pytest.mark.asyncio
async def test_epoch_poll_detects_mismatch_and_clears_cache():
    """P16 核心: 断开 → 远程 INCR → poll 检测不一致 → 清除本地缓存。

    模拟场景:
    1. Worker 有本地 epoch=5 for project_id
    2. 另一个 worker 直接 INCR Redis → remote epoch=6
    3. 本 worker 的 pub-sub 断连，未收到通知
    4. _epoch_poll_task 检测到 local(5) != remote(6) → 清缓存
    """
    redis = fakeredis_aio.FakeRedis()
    set_redis_client(redis)

    project_id = "test-project-poll-001"
    cleared_projects: list[str] = []

    def on_clear(pid: str):
        cleared_projects.append(pid)

    register_local_cache_clear(on_clear)

    try:
        # 1. 设置本地 epoch=5
        set_local_epoch(project_id, 5)

        # 2. 模拟远程 INCR（另一个 worker 直接写 Redis）
        key = f"{EPOCH_KEY_PREFIX}{project_id}"
        await redis.set(key, "6")

        # 3. 直接运行一次 poll 逻辑（不等 60s）
        # 使用 monkeypatch 把 EPOCH_POLL_INTERVAL 设为 0 并只运行一轮
        with patch(
            "app.services.acnr.cache_epoch.EPOCH_POLL_INTERVAL", 0
        ):
            # 创建 poll task 并让它跑一轮
            task = asyncio.create_task(_epoch_poll_task())
            await asyncio.sleep(0.1)  # 让 poll 运行一次
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 4. 验证：本地缓存被清除
        assert project_id in cleared_projects, (
            f"Expected {project_id} in cleared list, got {cleared_projects}"
        )
        # 本地 epoch 应更新为远程值
        assert _local_epoch_store.get(project_id) == 6

    finally:
        set_redis_client(None)
        await redis.aclose()


@pytest.mark.asyncio
async def test_epoch_poll_no_action_when_consistent():
    """轮询时本地 epoch 与远程一致 → 不清缓存。"""
    redis = fakeredis_aio.FakeRedis()
    set_redis_client(redis)

    project_id = "test-project-consistent"
    cleared_projects: list[str] = []

    def on_clear(pid: str):
        cleared_projects.append(pid)

    register_local_cache_clear(on_clear)

    try:
        # 本地和远程都是 epoch=3
        set_local_epoch(project_id, 3)
        key = f"{EPOCH_KEY_PREFIX}{project_id}"
        await redis.set(key, "3")

        with patch(
            "app.services.acnr.cache_epoch.EPOCH_POLL_INTERVAL", 0
        ):
            task = asyncio.create_task(_epoch_poll_task())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 不应清除任何缓存
        assert project_id not in cleared_projects

    finally:
        set_redis_client(None)
        await redis.aclose()


# ─── Test: 重连后清除全部本地缓存 [Req-14.2] ─────────────────────────────────


@pytest.mark.asyncio
async def test_reconnect_clears_all_local_caches():
    """重连成功后清除全部本地缓存 [Req-14.2]。"""
    cleared_projects: list[str] = []

    def on_clear(pid: str):
        cleared_projects.append(pid)

    register_local_cache_clear(on_clear)

    # 设置多个 project 的本地 epoch
    set_local_epoch("proj-a", 5)
    set_local_epoch("proj-b", 10)
    set_local_epoch("proj-c", 3)

    # _clear_all_local_caches 应清除全部
    _clear_all_local_caches()

    assert "proj-a" in cleared_projects
    assert "proj-b" in cleared_projects
    assert "proj-c" in cleared_projects
    assert len(_local_epoch_store) == 0


# ─── Test: 指数退避时序 [Req-14.1] ──────────────────────────────────────────


def test_reconnect_backoff_schedule():
    """指数退避 5s/10s/20s/30s max [Req-14.1]。"""
    assert RECONNECT_BACKOFF_SCHEDULE == [5, 10, 20, 30]

    # 超出索引范围时取最后一个（30s max）
    for attempt in range(10):
        idx = min(attempt, len(RECONNECT_BACKOFF_SCHEDULE) - 1)
        delay = RECONNECT_BACKOFF_SCHEDULE[idx]
        if attempt >= 3:
            assert delay == 30, f"attempt {attempt} should use 30s max, got {delay}"


# ─── Test: 断连重连循环逻辑 [Req-14.1] ──────────────────────────────────────


@pytest.mark.asyncio
async def test_reconnect_loop_retries_on_failure():
    """_reconnect_loop 在连接失败时重试（指数退避）[Req-14.1]。

    模拟 pubsub.psubscribe 抛异常 → 验证重试逻辑。
    """
    attempt_count = 0
    sleep_delays: list[float] = []

    class FakeRedisFailOnSubscribe:
        """模拟连接失败的 Redis。"""
        def pubsub(self):
            return FakePubSubFail()

    class FakePubSubFail:
        async def psubscribe(self, *args):
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionError("Redis connection lost")

    set_redis_client(FakeRedisFailOnSubscribe())

    original_sleep = asyncio.sleep

    async def mock_sleep(delay):
        sleep_delays.append(delay)
        if len(sleep_delays) >= 3:
            # 在第 3 次重试后取消任务
            raise asyncio.CancelledError()
        await original_sleep(0)  # yield control

    with patch("app.services.acnr.cache_epoch.asyncio.sleep", side_effect=mock_sleep):
        try:
            await _reconnect_loop()
        except asyncio.CancelledError:
            pass

    # 验证：尝试了 3 次连接
    assert attempt_count >= 3

    # 验证：退避时间递增
    assert sleep_delays[0] == 5   # 第 1 次退避
    assert sleep_delays[1] == 10  # 第 2 次退避
    assert sleep_delays[2] == 20  # 第 3 次退避


# ─── Test: Redis 完全不可用时降级 [Req-14.4] ─────────────────────────────────


@pytest.mark.asyncio
async def test_redis_unavailable_records_fallback_metric():
    """Redis 完全不可用 → epoch=0 + fallback metric [Req-14.4]。"""
    set_redis_client(None)

    with patch(
        "app.services.acnr.cache_epoch._record_fallback_metric"
    ) as mock_metric:
        epoch = await increment_epoch("some-project")
        assert epoch == 0
        mock_metric.assert_called()

        epoch2 = await get_epoch("some-project")
        assert epoch2 == 0
        assert mock_metric.call_count >= 2


# ─── Test: start/stop subscriber lifecycle ───────────────────────────────────


@pytest.mark.asyncio
async def test_start_stop_epoch_subscriber():
    """start_epoch_subscriber 创建后台任务，stop 能正常取消。"""
    redis = fakeredis_aio.FakeRedis()
    set_redis_client(redis)

    try:
        await start_epoch_subscriber()

        # 验证后台任务已创建
        from app.services.acnr import cache_epoch
        assert cache_epoch._subscriber_task is not None
        assert cache_epoch._poll_task is not None
        assert not cache_epoch._subscriber_task.done()
        assert not cache_epoch._poll_task.done()

        # 停止
        await stop_epoch_subscriber()
        assert cache_epoch._subscriber_task is None
        assert cache_epoch._poll_task is None

    finally:
        set_redis_client(None)
        await redis.aclose()


@pytest.mark.asyncio
async def test_start_subscriber_without_redis_skips():
    """Redis 不可用时 start_epoch_subscriber 跳过（不崩溃）。"""
    set_redis_client(None)

    await start_epoch_subscriber()  # 不应抛异常

    from app.services.acnr import cache_epoch
    assert cache_epoch._subscriber_task is None
    assert cache_epoch._poll_task is None


# ─── Test: 完整场景 — 断开 → 远程 INCR → poll 修复 [P16] ────────────────────


@pytest.mark.asyncio
async def test_full_scenario_disconnect_incr_poll_fix():
    """P16 完整集成场景:
    1. Worker 正常订阅，本地 epoch=1
    2. Pub-sub "断开"（模拟：不再通过 channel 收到消息）
    3. 远程 INCR → Redis epoch=2
    4. 本地 epoch 仍为 1（因断连未收到通知）
    5. Poll 检测到不一致 → 清缓存
    """
    redis = fakeredis_aio.FakeRedis()
    set_redis_client(redis)

    project_id = "test-full-scenario"
    cleared_projects: list[str] = []

    def on_clear(pid: str):
        cleared_projects.append(pid)

    register_local_cache_clear(on_clear)

    try:
        # 1. 正常 increment → 本地 epoch=1
        epoch = await increment_epoch(project_id)
        assert epoch == 1
        assert _local_epoch_store[project_id] == 1
        cleared_projects.clear()  # 清除 increment 时触发的本地通知

        # 2 + 3. 模拟断连期间另一个 worker INCR（直接操作 Redis）
        key = f"{EPOCH_KEY_PREFIX}{project_id}"
        await redis.incr(key)  # Redis epoch 变为 2

        # 4. 本地 epoch 仍为 1
        assert _local_epoch_store[project_id] == 1

        # 5. Poll 检测到不一致 → 清缓存
        with patch(
            "app.services.acnr.cache_epoch.EPOCH_POLL_INTERVAL", 0
        ):
            task = asyncio.create_task(_epoch_poll_task())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 验证：缓存被清除 + 本地 epoch 更新
        assert project_id in cleared_projects
        assert _local_epoch_store[project_id] == 2

    finally:
        await stop_epoch_subscriber()
        set_redis_client(None)
        await redis.aclose()
