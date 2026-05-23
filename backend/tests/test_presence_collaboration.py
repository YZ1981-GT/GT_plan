"""Presence 协同感知服务测试

Validates: workpaper-collaboration-presence F2 + F3
"""
import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.presence_service import PresenceService


@pytest.fixture
def mock_redis():
    """创建 mock Redis 实例"""
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zrem = AsyncMock()
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hdel = AsyncMock()
    redis.scan_iter = MagicMock(return_value=iter([]))
    return redis


@pytest.fixture
def service(mock_redis):
    return PresenceService(mock_redis)


class TestPresenceHeartbeat:
    """心跳上报测试"""

    @pytest.mark.asyncio
    async def test_heartbeat_updates_zset(self, service, mock_redis):
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await service.heartbeat(
            project_id=project_id,
            user_id=user_id,
            user_name="张三",
            view_name="workpaper_editor",
        )

        mock_redis.zadd.assert_called_once()
        call_args = mock_redis.zadd.call_args
        key = call_args[0][0]
        assert f"presence:{project_id}:workpaper_editor" == key

    @pytest.mark.asyncio
    async def test_heartbeat_with_editing_info(self, service, mock_redis):
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await service.heartbeat(
            project_id=project_id,
            user_id=user_id,
            user_name="李四",
            view_name="adjustments",
            editing_info={"account_code": "1001", "entry_group_id": "eg-1"},
        )

        # Should also write to editing hash
        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        key = call_args[0][0]
        assert f"presence:editing:{project_id}" == key


class TestPresenceOnlineMembers:
    """在线成员查询测试"""

    @pytest.mark.asyncio
    async def test_get_online_members_filters_expired(self, service, mock_redis):
        project_id = uuid.uuid4()
        now = time.time()

        # 模拟一个活跃用户和一个过期用户
        mock_redis.zrangebyscore = AsyncMock(return_value=[
            (f"user-1|张三", now - 10),  # 10s ago, active
            # expired ones are filtered by zrangebyscore min parameter
        ])

        members = await service.get_online_members(project_id, view_name="workpaper_editor")

        assert len(members) == 1
        assert members[0]["user_name"] == "张三"
        assert members[0]["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_get_online_members_empty_when_no_users(self, service, mock_redis):
        project_id = uuid.uuid4()
        mock_redis.zrangebyscore = AsyncMock(return_value=[])

        members = await service.get_online_members(project_id, view_name="workpaper_editor")
        assert members == []


class TestPresenceRemoveUser:
    """用户离开测试"""

    @pytest.mark.asyncio
    async def test_remove_user_cleans_zset_and_hash(self, service, mock_redis):
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_redis.zrangebyscore = AsyncMock(return_value=[
            f"{user_id}|张三",
        ])

        await service.remove_user(project_id, user_id, "workpaper_editor")

        # Should remove from ZSET
        mock_redis.zrem.assert_called()
        # Should remove from editing hash
        mock_redis.hdel.assert_called_once()


class TestPresenceCleanup:
    """过期清理测试"""

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_stale_entries(self, service, mock_redis):
        project_id = uuid.uuid4()
        now = time.time()

        # Mock scan_iter to return one key (async generator with match kwarg)
        async def mock_scan(**kwargs):
            yield f"presence:{project_id}:workpaper_editor"

        mock_redis.scan_iter = mock_scan

        # Mock expired members
        mock_redis.zrangebyscore = AsyncMock(return_value=[
            "expired-user|过期用户",
        ])

        cleaned = await service.cleanup_expired(project_id)

        assert cleaned == 1
        mock_redis.zrem.assert_called()


class TestPresenceRedisUnavailable:
    """Redis 不可用降级测试 — 验证 service 层抛异常（由调用方 try/except）"""

    @pytest.mark.asyncio
    async def test_heartbeat_raises_when_redis_down(self, mock_redis):
        mock_redis.zadd = AsyncMock(side_effect=ConnectionError("Redis down"))
        service = PresenceService(mock_redis)

        # PresenceService 本身不吞异常，由 router 层 try/except 处理
        with pytest.raises(ConnectionError):
            await service.heartbeat(
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                user_name="测试",
                view_name="test",
            )

    @pytest.mark.asyncio
    async def test_get_online_members_raises_on_error(self, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(side_effect=ConnectionError("Redis down"))
        service = PresenceService(mock_redis)

        with pytest.raises(ConnectionError):
            await service.get_online_members(uuid.uuid4(), "test")
