"""PBT: epoch 单调递增 — 并发 INCR [P8]

**Validates: Requirements 7.1, 7.2**

Property: 对同一 project 并发调用 increment_epoch N 次，
          返回值序列严格单调递增（无重复、无回退）。

使用 fakeredis 模拟 Redis INCR + pub-sub，验证并发安全性。
"""
from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ─── fakeredis setup ─────────────────────────────────────────────────────────

import fakeredis.aioredis as fakeredis_aio

# ─── Import SUT ──────────────────────────────────────────────────────────────

from app.services.acnr.cache_epoch import (
    EPOCH_KEY_PREFIX,
    get_epoch,
    get_redis_client,
    increment_epoch,
    set_redis_client,
)


# ─── Strategies ──────────────────────────────────────────────────────────────

_project_id_st = st.uuids().map(str)
_concurrency_st = st.integers(min_value=2, max_value=10)


# ─── Tests ───────────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(project_id=_project_id_st, n_calls=_concurrency_st)
def test_epoch_monotonic_sequential(project_id: str, n_calls: int):
    """P8: 顺序调用 increment_epoch N 次，返回值严格单调递增。"""

    async def _run():
        # 每次测试用独立 fakeredis 实例
        redis = fakeredis_aio.FakeRedis()
        set_redis_client(redis)

        try:
            epochs = []
            for _ in range(n_calls):
                e = await increment_epoch(project_id)
                epochs.append(e)

            # 严格单调递增
            for i in range(1, len(epochs)):
                assert epochs[i] > epochs[i - 1], (
                    f"epoch not monotonic: epochs[{i-1}]={epochs[i-1]}, "
                    f"epochs[{i}]={epochs[i]}"
                )

            # 第一个值 >= 1（INCR 从 0 开始，第一次返回 1）
            assert epochs[0] >= 1

            # get_epoch 应返回最新值
            current = await get_epoch(project_id)
            assert current == epochs[-1]
        finally:
            set_redis_client(None)
            await redis.aclose()

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(project_id=_project_id_st, n_calls=_concurrency_st)
def test_epoch_monotonic_concurrent(project_id: str, n_calls: int):
    """P8: 并发调用 increment_epoch N 次，返回值集合大小 == N 且全正。"""

    async def _run():
        redis = fakeredis_aio.FakeRedis()
        set_redis_client(redis)

        try:
            # 并发 fire N 个 increment_epoch
            tasks = [increment_epoch(project_id) for _ in range(n_calls)]
            results = await asyncio.gather(*tasks)

            # 所有返回值 > 0
            assert all(e > 0 for e in results), f"有 0 值: {results}"

            # 返回值互不相同（INCR 保证原子递增，无重复）
            assert len(set(results)) == n_calls, (
                f"并发 INCR 产生重复: {sorted(results)}"
            )

            # 排序后严格单调递增
            sorted_results = sorted(results)
            for i in range(1, len(sorted_results)):
                assert sorted_results[i] > sorted_results[i - 1]

            # 最终 epoch == max(results)
            current = await get_epoch(project_id)
            assert current == max(results)
        finally:
            set_redis_client(None)
            await redis.aclose()

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(project_id=_project_id_st)
def test_epoch_redis_unavailable_fallback(project_id: str):
    """P8 降级: Redis 不可用时，epoch 返回 0（不抛异常）。"""

    async def _run():
        # 不注入 redis client → get_redis_client() returns None
        set_redis_client(None)

        epoch = await increment_epoch(project_id)
        assert epoch == 0, "Redis 不可用时应返回 0"

        current = await get_epoch(project_id)
        assert current == 0, "Redis 不可用时 get_epoch 应返回 0"

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(
    project_a=_project_id_st,
    project_b=st.uuids().map(str),
)
def test_epoch_project_isolation(project_a: str, project_b: str):
    """P8 隔离: 不同 project 的 epoch 互不影响。"""
    if project_a == project_b:
        return  # skip trivial case

    async def _run():
        redis = fakeredis_aio.FakeRedis()
        set_redis_client(redis)

        try:
            # project_a 递增 3 次
            for _ in range(3):
                await increment_epoch(project_a)

            # project_b 递增 1 次
            await increment_epoch(project_b)

            epoch_a = await get_epoch(project_a)
            epoch_b = await get_epoch(project_b)

            assert epoch_a == 3
            assert epoch_b == 1
        finally:
            set_redis_client(None)
            await redis.aclose()

    asyncio.run(_run())


@settings(max_examples=5, deadline=None)
@given(project_id=_project_id_st, n_calls=_concurrency_st)
def test_epoch_publish_called_on_incr(project_id: str, n_calls: int):
    """P8 pub-sub: increment_epoch 后发布到 acnr:invalidate:{project_id} 频道。"""

    async def _run():
        redis = fakeredis_aio.FakeRedis()
        set_redis_client(redis)

        try:
            # 订阅频道
            pubsub = redis.pubsub()
            channel = f"acnr:invalidate:{project_id}"
            await pubsub.subscribe(channel)

            # 递增 N 次
            for _ in range(n_calls):
                await increment_epoch(project_id)

            # 读取订阅消息（跳过 subscribe 确认消息）
            messages = []
            for _ in range(n_calls + 1):  # +1 for subscribe confirmation
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    messages.append(msg)

            # 至少收到 n_calls 条消息（pub-sub 可能有延迟，但 fakeredis 同步）
            assert len(messages) >= n_calls, (
                f"Expected {n_calls} messages, got {len(messages)}"
            )

            await pubsub.unsubscribe(channel)
        finally:
            set_redis_client(None)
            await redis.aclose()

    asyncio.run(_run())
