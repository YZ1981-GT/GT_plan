"""trust_score_service 单元测试 — V3 收官增强 Req 9.7

验证：
1. aggregate_trust_score 返回正确结构（5 层数据）
2. hash_context 生成一致的哈希
3. _parse_context 正确解析各种格式
4. Redis 缓存命中时直接返回
5. Redis 不可用时降级正常工作

Validates: Requirements 9.7
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.trust_score_service import (
    CACHE_TTL_SECONDS,
    TrustScorePayload,
    _parse_context,
    aggregate_trust_score,
    hash_context,
    invalidate_trust_cache,
)


# ---------------------------------------------------------------------------
# hash_context
# ---------------------------------------------------------------------------


class TestHashContext:
    def test_consistent_hash(self):
        """相同输入产生相同哈希。"""
        ctx = "workpaper:D2-1|cells.B5"
        assert hash_context(ctx) == hash_context(ctx)

    def test_different_inputs_different_hash(self):
        """不同输入产生不同哈希。"""
        assert hash_context("workpaper:D2-1|cells.B5") != hash_context("report:BS|A.1")

    def test_hash_length(self):
        """哈希长度为 16 字符。"""
        assert len(hash_context("any_context")) == 16


# ---------------------------------------------------------------------------
# _parse_context
# ---------------------------------------------------------------------------


class TestParseContext:
    def test_full_format(self):
        """完整格式：namespace:identifier|cell。"""
        ns, ident, cell = _parse_context("workpaper:D2-1|cells.B5")
        assert ns == "workpaper"
        assert ident == "D2-1"
        assert cell == "cells.B5"

    def test_no_cell(self):
        """无 cell 部分。"""
        ns, ident, cell = _parse_context("tb:1001")
        assert ns == "tb"
        assert ident == "1001"
        assert cell is None

    def test_report_format(self):
        """报表格式。"""
        ns, ident, cell = _parse_context("report:soe_consolidated|A.5")
        assert ns == "report"
        assert ident == "soe_consolidated"
        assert cell == "A.5"

    def test_no_colon(self):
        """无冒号时 namespace 为整个 base。"""
        ns, ident, cell = _parse_context("simple")
        assert ns == "simple"
        assert ident == ""
        assert cell is None

    def test_multiple_pipes(self):
        """多个 | 时只取第一个分割。"""
        ns, ident, cell = _parse_context("workpaper:D2-1|sheet1|B5")
        assert ns == "workpaper"
        assert ident == "D2-1"
        assert cell == "sheet1|B5"


# ---------------------------------------------------------------------------
# aggregate_trust_score
# ---------------------------------------------------------------------------


class TestAggregateTrustScore:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """返回包含 5 层数据的正确结构。"""
        db = AsyncMock()
        # Mock execute to return empty results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        result = await aggregate_trust_score(
            db,
            project_id=project_id,
            context="workpaper:D2-1|cells.B5",
            redis=None,
        )

        # 验证结构
        assert "penetration" in result
        assert "history" in result
        assert "ai" in result
        assert "formula" in result
        assert "consistency" in result

        # penetration 应有 5 层
        assert isinstance(result["penetration"], list)
        assert len(result["penetration"]) == 5

        # formula 应为 dict
        assert isinstance(result["formula"], dict)
        assert result["formula"]["status"] == "placeholder"

        # consistency 应为 dict
        assert isinstance(result["consistency"], dict)
        assert "is_synced" in result["consistency"]
        assert "has_pending_ai" in result["consistency"]

    @pytest.mark.asyncio
    async def test_redis_cache_hit(self):
        """Redis 缓存命中时直接返回缓存数据。"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        context = "report:BS|A.1"

        cached_payload = {
            "penetration": [],
            "history": [],
            "ai": [],
            "formula": None,
            "consistency": {"is_synced": True},
        }

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached_payload))

        result = await aggregate_trust_score(
            db,
            project_id=project_id,
            context=context,
            redis=redis,
        )

        assert result == cached_payload
        # DB 不应被调用
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_cache_miss_writes_cache(self):
        """Redis 缓存未命中时查询 DB 并写入缓存。"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()
        context = "tb:1001"

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        result = await aggregate_trust_score(
            db,
            project_id=project_id,
            context=context,
            redis=redis,
        )

        # 验证写入缓存
        redis.set.assert_called_once()
        call_args = redis.set.call_args
        assert call_args[1]["ex"] == CACHE_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_gracefully(self):
        """Redis 不可用时降级正常工作（不报错）。"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=mock_result)

        project_id = uuid.uuid4()

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("Redis connection refused"))
        redis.set = AsyncMock(side_effect=Exception("Redis connection refused"))

        # 不应抛异常
        result = await aggregate_trust_score(
            db,
            project_id=project_id,
            context="workpaper:D2-1|cells.B5",
            redis=redis,
        )

        assert "penetration" in result
        assert "consistency" in result


# ---------------------------------------------------------------------------
# invalidate_trust_cache
# ---------------------------------------------------------------------------


class TestInvalidateTrustCache:
    @pytest.mark.asyncio
    async def test_no_redis_returns_zero(self):
        """无 Redis 时返回 0。"""
        result = await invalidate_trust_cache(uuid.uuid4(), redis=None)
        assert result == 0

    @pytest.mark.asyncio
    async def test_deletes_matching_keys(self):
        """删除匹配的缓存 key。"""
        project_id = uuid.uuid4()
        redis = AsyncMock()

        # Mock scan_iter to return some keys
        async def mock_scan_iter(**kwargs):
            for key in [f"trust:{project_id}:abc123", f"trust:{project_id}:def456"]:
                yield key

        redis.scan_iter = mock_scan_iter
        redis.delete = AsyncMock()

        result = await invalidate_trust_cache(project_id, redis=redis)
        assert result == 2
        redis.delete.assert_called_once()
