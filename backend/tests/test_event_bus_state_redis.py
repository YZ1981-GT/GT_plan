"""E2：Redis 版 `EventBusStateAdapter` 的守卫（用假 Redis，不需要真实例）。

判据要点：
1. **pending 三方法必须显式抛 `NotImplementedError`** —— 多 worker 下若静默返回 None，
   同一事件会被每个 worker 各自 debounce 一次（重复派发），比直接崩更难查。
2. **配额必须原子** —— 用假 Redis 记录 Lua 调用次数与参数，断言：
   - `acquire` 走 `eval` 而不是 `get`+`incr` 两步（两步在并发下会双放）；
   - `release` 走 `eval`（防止减成负数）。
3. **TTL 必须带上** —— 崩溃不调 release 时靠它回收，否则计数只增不减会永久锁死项目。
4. **`max_per_project <= 0` 语义** —— 生产默认 0 表示不限，不能当成「禁止连接」。
5. **后端故障降级放行** —— 配额服务挂了不应阻断事件流（SSE 是只读通知，不是写路径）。
"""
from __future__ import annotations

import uuid

import pytest

from app.services.event_bus_state_adapter import EventBusStateAdapter
from app.services.event_bus_state_redis import (
    DEFAULT_QUOTA_TTL_SECONDS,
    QUOTA_KEY_PREFIX,
    RedisEventBusStateAdapter,
)


class _FakeRedis:
    """记录 eval 调用；用 dict 模拟计数。"""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.eval_calls: list[tuple[str, int, tuple]] = []
        self.get_calls: list[str] = []
        self.fail: Exception | None = None

    async def eval(self, script: str, numkeys: int, *args) -> int:
        if self.fail is not None:
            raise self.fail
        self.eval_calls.append((script, numkeys, args))
        key, *rest = args
        current = self.counts.get(key, 0)
        if "INCR" in script:
            limit, _ttl = int(rest[0]), int(rest[1])
            if current >= limit:
                return 0
            self.counts[key] = current + 1
            return 1
        # 释放脚本：**按脚本原文里的守卫模拟**，而不是无条件按「当前值 <= 0 就 no-op」。
        # 🔴 这是变异逼出来的：原实现无条件 no-op，于是把生产 Lua 的
        # `if cur <= 0 then return 0 end` 去掉后，假 Redis 照样返回 0、用例仍绿
        # —— 等于这条守卫在测假对象的行为，不是生产脚本。
        if "if cur <= 0 then return 0 end" in script and current <= 0:
            return 0
        self.counts[key] = current - 1
        return 1

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        value = self.counts.get(key)
        return None if value is None else str(value)


def _adapter(**kwargs) -> tuple[RedisEventBusStateAdapter, _FakeRedis]:
    fake = _FakeRedis()
    return RedisEventBusStateAdapter(fake, **kwargs), fake


# ---------------------------------------------------------------------------
# 判据 1：pending 三方法显式不支持
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, args",
    [
        ("get_pending_payload", ("k",)),
        ("set_pending_payload", ("k", {"a": 1})),
        ("pop_pending_payload", ("k",)),
    ],
)
@pytest.mark.asyncio
async def test_pending_methods_raise_instead_of_silently_dropping(method: str, args: tuple):
    adapter, _fake = _adapter()
    with pytest.raises(NotImplementedError, match="TimerHandle"):
        await getattr(adapter, method)(*args)


# ---------------------------------------------------------------------------
# 判据 2：配额原子（走 eval，不是 get+incr）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_uses_atomic_eval_not_two_step():
    adapter, fake = _adapter()
    project = uuid.uuid4()
    allowed = await adapter.acquire_sse_quota(project, 2)
    assert allowed is True
    assert len(fake.eval_calls) == 1, "acquire 必须一次 eval 完成，不能 get + incr 两步"
    assert fake.get_calls == [], "acquire 不应使用非原子的 get"
    script, numkeys, args = fake.eval_calls[0]
    assert "INCR" in script and numkeys == 1
    assert args[0] == f"{QUOTA_KEY_PREFIX}{project}"


@pytest.mark.asyncio
async def test_acquire_rejects_at_limit_and_release_frees():
    adapter, fake = _adapter()
    project = uuid.uuid4()
    assert await adapter.acquire_sse_quota(project, 2) is True
    assert await adapter.acquire_sse_quota(project, 2) is True
    assert await adapter.acquire_sse_quota(project, 2) is False, "超过上限必须拒绝"
    assert fake.counts[f"{QUOTA_KEY_PREFIX}{project}"] == 2

    await adapter.release_sse_quota(project)
    assert await adapter.acquire_sse_quota(project, 2) is True


@pytest.mark.asyncio
async def test_release_is_idempotent_and_never_negative():
    adapter, fake = _adapter()
    project = uuid.uuid4()
    await adapter.release_sse_quota(project)
    await adapter.release_sse_quota(project)
    assert fake.counts.get(f"{QUOTA_KEY_PREFIX}{project}", 0) == 0, "释放不得把计数打成负数"


# ---------------------------------------------------------------------------
# 判据 3：TTL 必须随申请带上
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_passes_ttl_so_crashed_workers_get_reclaimed():
    adapter, fake = _adapter(quota_ttl_seconds=120)
    await adapter.acquire_sse_quota(uuid.uuid4(), 5)
    _script, _numkeys, args = fake.eval_calls[0]
    assert int(args[2]) == 120, "TTL 必须传给 Redis，否则崩溃留下的计数永不回收"
    assert DEFAULT_QUOTA_TTL_SECONDS > 0


# ---------------------------------------------------------------------------
# 判据 4：max_per_project <= 0 = 不限（生产默认）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [0, -1])
async def test_non_positive_cap_means_unlimited(cap: int):
    adapter, fake = _adapter()
    assert await adapter.acquire_sse_quota(uuid.uuid4(), cap) is True, (
        "生产默认 max_per_project=0 表示不限；当成「禁止连接」会让 SSE 全挂"
    )
    assert fake.eval_calls == [], "不限时不应触碰 Redis"


# ---------------------------------------------------------------------------
# 判据 5：后端故障降级放行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backend_failure_degrades_open_and_does_not_raise():
    adapter, fake = _adapter()
    fake.fail = RuntimeError("redis down")
    assert await adapter.acquire_sse_quota(uuid.uuid4(), 5) is True, (
        "配额后端故障应降级放行（SSE 是只读通知），不能阻断事件流"
    )
    # 释放失败同样不能抛
    await adapter.release_sse_quota(uuid.uuid4())


# ---------------------------------------------------------------------------
# 判据 6：契约一致性（能被 install 注入，且是 ABC 子类）
# ---------------------------------------------------------------------------


def test_adapter_implements_contract_and_requires_redis():
    adapter, _fake = _adapter()
    assert isinstance(adapter, EventBusStateAdapter)
    with pytest.raises(ValueError, match="Redis"):
        RedisEventBusStateAdapter(None)


def test_invalid_ttl_rejected():
    with pytest.raises(ValueError, match="quota_ttl_seconds"):
        RedisEventBusStateAdapter(_FakeRedis(), quota_ttl_seconds=0)
