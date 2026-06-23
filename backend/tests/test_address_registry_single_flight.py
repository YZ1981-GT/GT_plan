"""Tests: Address Registry single-flight + incremental invalidation

验证：
1. 并发 cache miss → DB 查询仅 1 次（single-flight）
2. 增量 invalidate_async(wp_id=X) → 仅影响目标 wp
3. exists(domain, uri) 定点检查
"""

from __future__ import annotations

import asyncio
import time as _time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.address_registry import AddressRegistryService, AddressEntry, _CacheSlot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """每个测试独立的 AddressRegistryService 实例"""
    svc = AddressRegistryService()
    return svc


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_entry(uri: str, domain: str = "wp", label: str = "test") -> AddressEntry:
    return AddressEntry(
        uri=uri,
        domain=domain,
        source="A1",
        path="cell",
        cell="B1",
        label=label,
        formula_ref=uri,
        account_code="",
        row_code="",
    )


# ---------------------------------------------------------------------------
# Test: single-flight — concurrent cache miss → DB query = 1
# ---------------------------------------------------------------------------

class TestSingleFlight:
    """并发 cache miss 时仅执行 1 次 DB 构建"""

    @pytest.mark.asyncio
    async def test_concurrent_miss_single_db_call(self, registry, mock_db):
        """N 个并发请求同时 miss → build_workpaper_entries 仅调用 1 次"""
        call_count = 0
        entries = [_make_entry("wp://A1/cell#B1")]

        async def mock_build(db, pid, year):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # 模拟 DB 耗时
            return entries

        with patch("app.services.address_registry.build_workpaper_entries", side_effect=mock_build):
            with patch.object(registry, '_redis_get', new_callable=AsyncMock, return_value=None):
                with patch.object(registry, '_redis_set', new_callable=AsyncMock):
                    # 启动 5 个并发请求
                    tasks = [
                        registry._get_domain(mock_db, "proj1", 2025, "soe", "wp")
                        for _ in range(5)
                    ]
                    results = await asyncio.gather(*tasks)

        # 核心断言：DB 构建仅执行 1 次
        assert call_count == 1
        # 所有请求拿到相同结果
        for r in results:
            assert r == entries

    @pytest.mark.asyncio
    async def test_l1_hit_no_lock(self, registry, mock_db):
        """L1 命中时不获取锁（快路径）"""
        entries = [_make_entry("wp://A1/cell#B1")]
        key = registry._slot_key("proj1", 2025, "soe", "wp")
        registry._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain="wp"
        )

        result = await registry._get_domain(mock_db, "proj1", 2025, "soe", "wp")
        assert result == entries


# ---------------------------------------------------------------------------
# Test: incremental invalidation
# ---------------------------------------------------------------------------

class TestIncrementalInvalidation:
    """invalidate_async(wp_id=X) 仅影响目标 wp"""

    @pytest.mark.asyncio
    async def test_incremental_invalidate_only_target_wp(self, registry):
        """增量失效：只清除包含目标 wp_id 的缓存，不影响其他"""
        key = registry._slot_key("proj1", 2025, "soe", "wp")
        entries = [
            _make_entry("wp://A1/cell#B1"),       # wp_id=A1
            _make_entry("wp://B2/cell#C3"),       # wp_id=B2
            _make_entry("wp://target_wp/cell#D4"),  # 目标 wp
        ]
        registry._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain="wp"
        )

        with patch.object(registry, '_redis_delete_many', new_callable=AsyncMock):
            await registry.invalidate_async("proj1", domain="wp", wp_id="target_wp")

        # 包含 target_wp 的 slot 应被清除（整个 slot 重建）
        assert key not in registry._slots

    @pytest.mark.asyncio
    async def test_full_invalidate_without_wp_id(self, registry):
        """不传 wp_id 时执行全量失效（原行为不变）"""
        key = registry._slot_key("proj1", 2025, "soe", "wp")
        entries = [_make_entry("wp://A1/cell#B1")]
        registry._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain="wp"
        )

        with patch.object(registry, '_redis_delete_many', new_callable=AsyncMock):
            await registry.invalidate_async("proj1", domain="wp")

        assert key not in registry._slots

    @pytest.mark.asyncio
    async def test_incremental_does_not_affect_other_domains(self, registry):
        """增量失效 wp 域不影响 tb 域"""
        wp_key = registry._slot_key("proj1", 2025, "soe", "wp")
        tb_key = registry._slot_key("proj1", 2025, "soe", "tb")

        registry._slots[wp_key] = _CacheSlot(
            entries=[_make_entry("wp://target/cell#A1", "wp")],
            built_at=_time.time(), domain="wp"
        )
        registry._slots[tb_key] = _CacheSlot(
            entries=[_make_entry("tb://1001#审定数", "tb")],
            built_at=_time.time(), domain="tb"
        )

        with patch.object(registry, '_redis_delete_many', new_callable=AsyncMock):
            await registry.invalidate_async("proj1", domain="wp", wp_id="target")

        # tb 域不受影响
        assert tb_key in registry._slots


# ---------------------------------------------------------------------------
# Test: exists() point-check
# ---------------------------------------------------------------------------

class TestExists:
    """exists(domain, uri) 定点检查"""

    @pytest.mark.asyncio
    async def test_exists_returns_true(self, registry, mock_db):
        """URI 存在时返回 True"""
        entries = [_make_entry("wp://A1/cell#B1", "wp")]
        key = registry._slot_key("proj1", 2025, "soe", "wp")
        registry._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain="wp"
        )

        result = await registry.exists(mock_db, "proj1", 2025, "wp", "wp://A1/cell#B1")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false(self, registry, mock_db):
        """URI 不存在时返回 False"""
        entries = [_make_entry("wp://A1/cell#B1", "wp")]
        key = registry._slot_key("proj1", 2025, "soe", "wp")
        registry._slots[key] = _CacheSlot(
            entries=entries, built_at=_time.time(), domain="wp"
        )

        result = await registry.exists(mock_db, "proj1", 2025, "wp", "wp://NONEXIST/cell#X9")
        assert result is False
