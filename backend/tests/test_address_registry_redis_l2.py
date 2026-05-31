"""
地址库 Redis 二级缓存 单元测试

**Validates: Requirements 1.1, 1.2, 1.3**

验证：
1. get_domain/get_all 先查 Redis L2，命中反序列化返回（跳过 DB）
2. Redis 未命中时走 DB 构建后回写 Redis（TTL 对齐按域）
3. invalidate/invalidate_all 同步删 Redis key（L1 + L2 同步失效）
"""
import json
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.address_registry import (
    AddressEntry,
    AddressRegistryService,
)


def _make_entry(domain: str = "tb", uri: str = "tb://1001#审定数") -> AddressEntry:
    return AddressEntry(
        uri=uri,
        domain=domain,
        source="1001",
        path="",
        cell="审定数",
        label="试算表 > 1001 > 审定数",
        formula_ref="TB('1001','审定数')",
    )


@pytest.fixture
def service():
    """每个测试一个干净的 AddressRegistryService 实例"""
    return AddressRegistryService()


@pytest.fixture
def fake_redis():
    """模拟 Redis 客户端"""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.scan = AsyncMock(return_value=(0, []))
    r.ping = AsyncMock()
    return r


class TestRedisL2Get:
    """需求 1.1: get_domain 先查 Redis L2，命中反序列化返回"""

    @pytest.mark.asyncio
    async def test_l2_hit_skips_db(self, service, fake_redis):
        """Redis L2 命中时不走 DB 构建"""
        entry = _make_entry()
        cached_json = json.dumps([asdict(entry)])
        fake_redis.get = AsyncMock(return_value=cached_json)

        with patch.object(service, "_get_redis", return_value=fake_redis):
            # 不传真实 db，如果走 DB 会报错
            result = await service.get_domain(None, "proj1", 2025, "soe", "tb")

        assert len(result) == 1
        assert result[0].uri == "tb://1001#审定数"
        assert result[0].domain == "tb"
        assert result[0].label == "试算表 > 1001 > 审定数"

    @pytest.mark.asyncio
    async def test_l2_hit_populates_l1(self, service, fake_redis):
        """Redis L2 命中后回填 L1 内存缓存"""
        entry = _make_entry()
        cached_json = json.dumps([asdict(entry)])
        fake_redis.get = AsyncMock(return_value=cached_json)

        with patch.object(service, "_get_redis", return_value=fake_redis):
            await service.get_domain(None, "proj1", 2025, "soe", "tb")

        # L1 应有缓存
        key = service._slot_key("proj1", 2025, "soe", "tb")
        assert key in service._slots
        assert len(service._slots[key].entries) == 1

    @pytest.mark.asyncio
    async def test_l1_hit_skips_redis_and_db(self, service, fake_redis):
        """L1 内存命中时不查 Redis 也不查 DB"""
        entry = _make_entry()
        from app.services.address_registry import _CacheSlot
        key = service._slot_key("proj1", 2025, "soe", "tb")
        service._slots[key] = _CacheSlot(
            entries=[entry], built_at=time.time(), domain="tb"
        )

        with patch.object(service, "_get_redis", return_value=fake_redis):
            result = await service.get_domain(None, "proj1", 2025, "soe", "tb")

        assert len(result) == 1
        # Redis 不应被调用
        fake_redis.get.assert_not_called()


class TestRedisL2Miss:
    """需求 1.2: Redis 未命中时走 DB 构建后回写 Redis"""

    @pytest.mark.asyncio
    async def test_l2_miss_builds_from_db_and_writes_back(self, service, fake_redis):
        """Redis 未命中 → DB 构建 → 回写 Redis（TTL 对齐）"""
        entry = _make_entry()
        fake_redis.get = AsyncMock(return_value=None)  # L2 miss

        with patch.object(service, "_get_redis", return_value=fake_redis), \
             patch(
                 "app.services.address_registry.build_trial_balance_entries",
                 new=AsyncMock(return_value=[entry])
             ):
            result = await service.get_domain(MagicMock(), "proj1", 2025, "soe", "tb")

        assert len(result) == 1
        assert result[0].uri == "tb://1001#审定数"

        # 验证回写 Redis 被调用，TTL = 60（tb 域）
        fake_redis.set.assert_called_once()
        call_args = fake_redis.set.call_args
        assert call_args.kwargs.get("ex") == 60  # tb TTL
        # key 格式正确
        redis_key = call_args.args[0]
        assert redis_key == "addr_reg:proj1:2025:soe:tb"

    @pytest.mark.asyncio
    async def test_l2_miss_report_domain_ttl_300(self, service, fake_redis):
        """report 域回写 TTL = 300"""
        entry = _make_entry(domain="report", uri="report://BS/BS-001#期末")
        fake_redis.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_redis", return_value=fake_redis), \
             patch(
                 "app.services.address_registry.build_report_entries",
                 new=AsyncMock(return_value=[entry])
             ):
            await service.get_domain(MagicMock(), "proj1", 2025, "soe", "report")

        call_args = fake_redis.set.call_args
        assert call_args.kwargs.get("ex") == 300  # report TTL


class TestRedisL2Invalidate:
    """需求 1.3: invalidate/invalidate_all 同步删 Redis key"""

    @pytest.mark.asyncio
    async def test_invalidate_async_deletes_redis_keys(self, service, fake_redis):
        """invalidate_async 删除匹配的 Redis keys"""
        from app.services.address_registry import _CacheSlot
        # 预填 L1
        key1 = service._slot_key("proj1", 2025, "soe", "tb")
        key2 = service._slot_key("proj1", 2025, "soe", "report")
        service._slots[key1] = _CacheSlot(entries=[], built_at=time.time(), domain="tb")
        service._slots[key2] = _CacheSlot(entries=[], built_at=time.time(), domain="report")

        with patch.object(service, "_get_redis", return_value=fake_redis):
            await service.invalidate_async("proj1", domain="tb")

        # L1 只删了 tb
        assert key1 not in service._slots
        assert key2 in service._slots

        # Redis delete 被调用，只删 tb key
        fake_redis.delete.assert_called_once()
        deleted_keys = fake_redis.delete.call_args.args
        assert "addr_reg:proj1:2025:soe:tb" in deleted_keys

    @pytest.mark.asyncio
    async def test_invalidate_all_async_flushes_redis(self, service, fake_redis):
        """invalidate_all_async 清空 L1 + scan 删 Redis L2"""
        from app.services.address_registry import _CacheSlot
        service._slots["proj1:2025:soe:tb"] = _CacheSlot(
            entries=[], built_at=time.time(), domain="tb"
        )

        # 模拟 scan 返回一些 keys
        fake_redis.scan = AsyncMock(return_value=(0, [b"addr_reg:proj1:2025:soe:tb"]))

        with patch.object(service, "_get_redis", return_value=fake_redis):
            await service.invalidate_all_async()

        assert len(service._slots) == 0
        fake_redis.scan.assert_called()
        fake_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_invalidate_sync_clears_l1_only(self, service):
        """同步 invalidate 仅清 L1（向后兼容）"""
        from app.services.address_registry import _CacheSlot
        key = service._slot_key("proj1", 2025, "soe", "tb")
        service._slots[key] = _CacheSlot(entries=[], built_at=time.time(), domain="tb")

        service.invalidate("proj1", domain="tb")

        assert key not in service._slots


class TestRedisL2Degradation:
    """Redis 不可用时降级到 DB 构建（不报错）"""

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_through_to_db(self, service):
        """Redis 返回 None 时直接走 DB 构建"""
        entry = _make_entry()

        with patch.object(service, "_get_redis", return_value=None), \
             patch(
                 "app.services.address_registry.build_trial_balance_entries",
                 new=AsyncMock(return_value=[entry])
             ):
            result = await service.get_domain(MagicMock(), "proj1", 2025, "soe", "tb")

        assert len(result) == 1
        assert result[0].uri == "tb://1001#审定数"

    @pytest.mark.asyncio
    async def test_redis_get_exception_falls_through(self, service, fake_redis):
        """Redis get 抛异常时降级到 DB"""
        entry = _make_entry()
        fake_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch.object(service, "_get_redis", return_value=fake_redis), \
             patch(
                 "app.services.address_registry.build_trial_balance_entries",
                 new=AsyncMock(return_value=[entry])
             ):
            result = await service.get_domain(MagicMock(), "proj1", 2025, "soe", "tb")

        assert len(result) == 1
