"""Tests for wp_sheet_lock_service — sheet 级软锁

Requirements: 6.1, 6.2, 6.4
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.wp_sheet_lock_service import (
    WpSheetLockService,
    SHEET_LOCK_EXPIRE_SECONDS,
)


@pytest.fixture
def mock_db():
    """Mock AsyncSession"""
    db = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return WpSheetLockService(mock_db)


class TestAcquireLock:
    """Requirement 6.1: 获取 sheet 软锁"""

    @pytest.mark.asyncio
    async def test_acquire_new_lock_when_no_existing(self, service, mock_db):
        """无现有锁时应成功获取新锁"""
        # Mock: 无现有锁
        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = None
        mock_db.execute.return_value = result_mock

        wp_id = uuid4()
        user_id = uuid4()

        result = await service.acquire_lock(
            wp_id=wp_id,
            sheet_name="Sheet1",
            user_id=user_id,
            user_name="张三",
        )

        assert result["acquired"] is True
        assert result["status"] == "acquired"
        assert result["locked_by"] == str(user_id)
        assert result["locked_by_name"] == "张三"

    @pytest.mark.asyncio
    async def test_acquire_renews_for_same_user(self, service, mock_db):
        """同一用户重复获取应续期"""
        user_id = uuid4()
        now = datetime.now(timezone.utc)

        existing = {
            "id": str(uuid4()),
            "locked_by": str(user_id),
            "locked_by_name": "张三",
            "acquired_at": now.isoformat(),
            "heartbeat_at": now,  # 未过期
        }

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = existing
        mock_db.execute.return_value = result_mock

        result = await service.acquire_lock(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=user_id,
            user_name="张三",
        )

        assert result["acquired"] is True
        assert result["status"] == "renewed"

    @pytest.mark.asyncio
    async def test_acquire_fails_when_other_user_holds(self, service, mock_db):
        """其他用户持有未过期锁时应返回冲突"""
        other_user_id = uuid4()
        now = datetime.now(timezone.utc)

        existing = {
            "id": str(uuid4()),
            "locked_by": str(other_user_id),
            "locked_by_name": "李四",
            "acquired_at": now.isoformat(),
            "heartbeat_at": now,  # 未过期
        }

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = existing
        mock_db.execute.return_value = result_mock

        result = await service.acquire_lock(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=uuid4(),
            user_name="王五",
        )

        assert result["acquired"] is False
        assert result["locked_by"] == str(other_user_id)
        assert result["locked_by_name"] == "李四"

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_existing_lock_expired(self, service, mock_db):
        """现有锁已过期时应释放旧锁并获取新锁"""
        other_user_id = uuid4()
        expired_time = datetime.now(timezone.utc) - timedelta(seconds=SHEET_LOCK_EXPIRE_SECONDS + 60)

        existing = {
            "id": str(uuid4()),
            "locked_by": str(other_user_id),
            "locked_by_name": "李四",
            "acquired_at": expired_time.isoformat(),
            "heartbeat_at": expired_time,  # 已过期
        }

        # 第一次 execute 返回 existing，后续返回 mock
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                result_mock = MagicMock()
                result_mock.mappings.return_value.first.return_value = existing
                return result_mock
            else:
                result_mock = MagicMock()
                result_mock.rowcount = 1
                return result_mock

        mock_db.execute = AsyncMock(side_effect=side_effect)

        result = await service.acquire_lock(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=uuid4(),
            user_name="王五",
        )

        assert result["acquired"] is True
        assert result["status"] == "acquired"


class TestReleaseLock:
    """Requirement 6.4: 释放锁"""

    @pytest.mark.asyncio
    async def test_release_returns_true_when_lock_exists(self, service, mock_db):
        """持有锁时释放应返回 True"""
        result_mock = MagicMock()
        result_mock.rowcount = 1
        mock_db.execute.return_value = result_mock

        released = await service.release_lock(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=uuid4(),
        )

        assert released is True

    @pytest.mark.asyncio
    async def test_release_returns_false_when_no_lock(self, service, mock_db):
        """无锁时释放应返回 False"""
        result_mock = MagicMock()
        result_mock.rowcount = 0
        mock_db.execute.return_value = result_mock

        released = await service.release_lock(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=uuid4(),
        )

        assert released is False


class TestHeartbeat:
    """心跳续期"""

    @pytest.mark.asyncio
    async def test_heartbeat_returns_true_when_lock_active(self, service, mock_db):
        """活跃锁心跳应返回 True"""
        result_mock = MagicMock()
        result_mock.rowcount = 1
        mock_db.execute.return_value = result_mock

        ok = await service.heartbeat(
            wp_id=uuid4(),
            sheet_name="Sheet1",
            user_id=uuid4(),
        )

        assert ok is True


class TestGetLockHolder:
    """Requirement 6.2: 查询锁持有者"""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_lock(self, service, mock_db):
        """无活跃锁时返回 None"""
        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = None
        mock_db.execute.return_value = result_mock

        holder = await service.get_lock_holder(
            wp_id=uuid4(),
            sheet_name="Sheet1",
        )

        assert holder is None

    @pytest.mark.asyncio
    async def test_returns_holder_info_when_lock_active(self, service, mock_db):
        """有活跃锁时返回持有者信息"""
        now = datetime.now(timezone.utc)
        row = {
            "locked_by": str(uuid4()),
            "locked_by_name": "张三",
            "acquired_at": now.isoformat(),
            "heartbeat_at": now.isoformat(),
        }

        result_mock = MagicMock()
        result_mock.mappings.return_value.first.return_value = row
        mock_db.execute.return_value = result_mock

        holder = await service.get_lock_holder(
            wp_id=uuid4(),
            sheet_name="Sheet1",
        )

        assert holder is not None
        assert holder["locked_by_name"] == "张三"
