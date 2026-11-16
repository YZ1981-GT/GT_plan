"""E2 骨架测试：EventBus 可外置状态 adapter 的行为契约（内存默认实现）。

- 默认 adapter 是 InMemoryEventBusStateAdapter
- 安装/重置可切换，互不污染
- InMemory 实现 debounce pending 行为与 dict 等价
- InMemory 实现 quota acquire / release 计数 + 超限拒绝
- 子类必须实现全部抽象方法（能被 isinstance 检查到）

真实 Redis / DB 实现与多 worker 零丢失验证属 E2 `[ ]*`，不在骨架内。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.services.event_bus_state_adapter import (
    EventBusStateAdapter,
    InMemoryEventBusStateAdapter,
    get_event_bus_state_adapter,
    install_event_bus_state_adapter,
    reset_event_bus_state_adapter,
)


@pytest.fixture(autouse=True)
def _reset_adapter():
    """每个用例结束恢复默认 adapter，避免互相污染。"""
    reset_event_bus_state_adapter()
    yield
    reset_event_bus_state_adapter()


def test_default_adapter_is_in_memory():
    adapter = get_event_bus_state_adapter()
    assert isinstance(adapter, InMemoryEventBusStateAdapter)


def test_install_replaces_singleton_and_reset_restores():
    custom = InMemoryEventBusStateAdapter()
    original = get_event_bus_state_adapter()
    assert custom is not original

    install_event_bus_state_adapter(custom)
    assert get_event_bus_state_adapter() is custom

    reset_event_bus_state_adapter()
    reset_adapter = get_event_bus_state_adapter()
    assert isinstance(reset_adapter, InMemoryEventBusStateAdapter)
    assert reset_adapter is not custom  # 新实例


@pytest.mark.asyncio
async def test_in_memory_pending_payload_round_trip():
    adapter = InMemoryEventBusStateAdapter()
    assert await adapter.get_pending_payload("k1") is None

    await adapter.set_pending_payload("k1", {"accounts": ["1001"]})
    assert await adapter.get_pending_payload("k1") == {"accounts": ["1001"]}

    # 覆盖写
    await adapter.set_pending_payload("k1", {"accounts": ["1001", "1002"]})
    popped = await adapter.pop_pending_payload("k1")
    assert popped == {"accounts": ["1001", "1002"]}
    assert await adapter.get_pending_payload("k1") is None


@pytest.mark.asyncio
async def test_in_memory_pop_missing_returns_none():
    adapter = InMemoryEventBusStateAdapter()
    assert await adapter.pop_pending_payload("nonexistent") is None


@pytest.mark.asyncio
async def test_in_memory_sse_quota_acquire_and_reject_when_full():
    adapter = InMemoryEventBusStateAdapter()
    project = uuid.uuid4()

    assert await adapter.acquire_sse_quota(project, max_per_project=2) is True
    assert await adapter.acquire_sse_quota(project, max_per_project=2) is True
    # 第三个超限
    assert await adapter.acquire_sse_quota(project, max_per_project=2) is False


@pytest.mark.asyncio
async def test_in_memory_sse_quota_release_frees_slot():
    adapter = InMemoryEventBusStateAdapter()
    project = uuid.uuid4()

    assert await adapter.acquire_sse_quota(project, 1) is True
    assert await adapter.acquire_sse_quota(project, 1) is False

    await adapter.release_sse_quota(project)
    assert await adapter.acquire_sse_quota(project, 1) is True


@pytest.mark.asyncio
async def test_in_memory_sse_quota_release_below_zero_is_noop():
    adapter = InMemoryEventBusStateAdapter()
    project = uuid.uuid4()
    # 多次释放不抛、不进负
    for _ in range(3):
        await adapter.release_sse_quota(project)
    assert await adapter.acquire_sse_quota(project, 1) is True


@pytest.mark.asyncio
async def test_in_memory_sse_quota_zero_cap_always_rejects():
    adapter = InMemoryEventBusStateAdapter()
    project = uuid.uuid4()
    assert await adapter.acquire_sse_quota(project, max_per_project=0) is False


@pytest.mark.asyncio
async def test_in_memory_sse_quota_isolates_projects():
    adapter = InMemoryEventBusStateAdapter()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    assert await adapter.acquire_sse_quota(p1, 1) is True
    # p1 用完不影响 p2
    assert await adapter.acquire_sse_quota(p2, 1) is True
    # p1 再申请仍超限
    assert await adapter.acquire_sse_quota(p1, 1) is False


def test_abstract_class_cannot_be_instantiated():
    """子类必须实现全部抽象方法；不加锁的契约在基类 docstring。"""
    with pytest.raises(TypeError):
        EventBusStateAdapter()  # type: ignore[abstract]


def test_custom_adapter_registration_is_isinstance_checkable():
    class _MyRedisAdapter(EventBusStateAdapter):
        async def get_pending_payload(self, dedup_key): return None
        async def set_pending_payload(self, dedup_key, payload): pass
        async def pop_pending_payload(self, dedup_key): return None
        async def acquire_sse_quota(self, project_id, max_per_project): return True
        async def release_sse_quota(self, project_id): pass

    adapter = _MyRedisAdapter()
    install_event_bus_state_adapter(adapter)
    got = get_event_bus_state_adapter()
    assert got is adapter
    assert isinstance(got, EventBusStateAdapter)
    assert not isinstance(got, InMemoryEventBusStateAdapter)


# ── E2 真实接线（2026-11-15）──────────────────────────────
#
# 🔴 骨架落地但生产零调用 = 死代码（memory「registry 成了只被测试看的副本」同型）。
# 以下用例钉住「EventBus 真的用了 adapter 的 SSE quota 面」。


@pytest.mark.asyncio
async def test_create_sse_queue_without_quota_keeps_legacy_behavior():
    """默认 `max_per_project=0` ⇒ 不申请配额，行为与改造前 100% 等价。"""
    from app.services.event_bus import EventBus

    bus = EventBus()
    q1 = await bus.create_sse_queue()
    q2 = await bus.create_sse_queue()
    assert len(bus._sse_queues) == 2
    assert q1 is not q2
    # 未传 project_id ⇒ 映射里是 None（不申请配额，但记录队列以便统一清理）
    assert set(bus._sse_queue_projects.values()) == {None}


@pytest.mark.asyncio
async def test_create_sse_queue_acquires_and_releases_quota():
    """传 project_id + cap ⇒ 走 adapter 配额；remove 时释放。"""
    from app.services.event_bus import EventBus
    from app.services.event_bus_state_adapter import (
        InMemoryEventBusStateAdapter,
        install_event_bus_state_adapter,
        reset_event_bus_state_adapter,
    )

    adapter = InMemoryEventBusStateAdapter()
    install_event_bus_state_adapter(adapter)
    try:
        bus = EventBus()
        project = uuid.uuid4()
        q = await bus.create_sse_queue(project_id=project, max_per_project=1)
        assert q is not None
        # 第二个应被拒
        with pytest.raises(Exception, match="已达上限"):
            await bus.create_sse_queue(project_id=project, max_per_project=1)
        # 释放后可再建
        bus.remove_sse_queue(q)
        await asyncio.sleep(0)  # 让 ensure_future 的 release 跑完
        q2 = await bus.create_sse_queue(project_id=project, max_per_project=1)
        assert q2 is not None
    finally:
        reset_event_bus_state_adapter()


@pytest.mark.asyncio
async def test_quota_isolated_per_project():
    """不同 project 的配额互不影响。"""
    from app.services.event_bus import EventBus
    from app.services.event_bus_state_adapter import (
        InMemoryEventBusStateAdapter,
        install_event_bus_state_adapter,
        reset_event_bus_state_adapter,
    )

    install_event_bus_state_adapter(InMemoryEventBusStateAdapter())
    try:
        bus = EventBus()
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        await bus.create_sse_queue(project_id=p1, max_per_project=1)
        # p1 满了，p2 仍可建
        await bus.create_sse_queue(project_id=p2, max_per_project=1)
        assert len(bus._sse_queues) == 2
    finally:
        reset_event_bus_state_adapter()


def test_create_sse_queue_is_async():
    """E2：必须是 async（quota 走 adapter 的 await）。

    🔴 这条钉住「改回同步」的回归：同步方法无法 await adapter，
    改回去会让配额静默失效。
    """
    import inspect

    from app.services.event_bus import EventBus

    assert inspect.iscoroutinefunction(EventBus.create_sse_queue)


def test_router_calls_create_sse_queue_with_await():
    """生产调用方必须 await（否则拿到 coroutine 而不是队列）。"""
    from pathlib import Path

    router = Path(__file__).resolve().parents[1] / "app" / "routers" / "events.py"
    source = router.read_text(encoding="utf-8")
    assert "await event_bus.create_sse_queue()" in source, (
        "routers/events.py 未 await create_sse_queue"
    )
