"""E2 骨架测试：EventBus 可外置状态 adapter 的行为契约（内存默认实现）。

- 默认 adapter 是 InMemoryEventBusStateAdapter
- 安装/重置可切换，互不污染
- InMemory 实现 debounce pending 行为与 dict 等价
- InMemory 实现 quota acquire / release 计数 + 超限拒绝
- 子类必须实现全部抽象方法（能被 isinstance 检查到）

真实 Redis / DB 实现与多 worker 零丢失验证属 E2 `[ ]*`，不在骨架内。
"""

from __future__ import annotations

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
