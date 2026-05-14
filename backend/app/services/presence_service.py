"""Presence Service — Redis ZSET 在线用户 + Hash 编辑状态

基于 Redis Sorted Set 追踪项目组成员当前所在视图，
基于 Redis Hash 追踪编辑锁定状态。

Redis Key 设计（from design.md D2）：
- presence:{project_id}:{view_name} → ZSET(user_id → unix_timestamp)
- presence:editing:{project_id} → HASH(user_id → JSON{view, account_code, entry_group_id, started_at})

心跳 30s 一次，60s 无心跳自动过期（ZRANGEBYSCORE 过滤）。

Validates: Requirements 2.1, 2.2, 2.3, 2.5
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# 心跳过期阈值（秒）
HEARTBEAT_EXPIRE_SECONDS = 60


class PresenceService:
    """在线感知服务"""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # ------------------------------------------------------------------
    # Key builders
    # ------------------------------------------------------------------

    @staticmethod
    def _presence_key(project_id: UUID, view_name: str) -> str:
        return f"presence:{project_id}:{view_name}"

    @staticmethod
    def _editing_key(project_id: UUID) -> str:
        return f"presence:editing:{project_id}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def heartbeat(
        self,
        project_id: UUID,
        user_id: UUID,
        user_name: str,
        view_name: str,
        editing_info: dict[str, Any] | None = None,
    ) -> None:
        """心跳上报：更新用户在线状态，可选更新编辑状态。

        Parameters
        ----------
        project_id : UUID
            项目 ID
        user_id : UUID
            用户 ID
        user_name : str
            用户姓名（用于前端展示）
        view_name : str
            当前视图名称（trial_balance / adjustments 等）
        editing_info : dict, optional
            编辑状态信息，如 {"account_code": "1001", "entry_group_id": "..."}
        """
        now = time.time()
        key = self._presence_key(project_id, view_name)

        # ZADD 更新在线状态（score = 当前时间戳）
        # 存储格式: member = "user_id|user_name" 便于查询时返回姓名
        member = f"{user_id}|{user_name}"
        await self._redis.zadd(key, {member: now})

        # 更新编辑状态（如果有）
        if editing_info:
            editing_key = self._editing_key(project_id)
            editing_data = {
                "view": view_name,
                "user_name": user_name,
                "started_at": editing_info.get("started_at", now),
                **editing_info,
            }
            await self._redis.hset(
                editing_key, str(user_id), json.dumps(editing_data, default=str)
            )

    async def get_online_members(
        self,
        project_id: UUID,
        view_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取当前在线成员列表。

        Parameters
        ----------
        project_id : UUID
            项目 ID
        view_name : str, optional
            视图名称过滤。为 None 时返回所有视图的在线成员。

        Returns
        -------
        list[dict]
            在线成员列表，每项含 user_id, user_name, view_name, last_heartbeat
        """
        cutoff = time.time() - HEARTBEAT_EXPIRE_SECONDS
        results: list[dict[str, Any]] = []

        if view_name:
            views = [view_name]
        else:
            # 扫描所有视图（通过 SCAN 匹配 presence:{project_id}:* ）
            pattern = f"presence:{project_id}:*"
            views = []
            async for key in self._redis.scan_iter(match=pattern):
                # key 格式: presence:{project_id}:{view_name}
                parts = key.split(":")
                if len(parts) >= 3:
                    views.append(":".join(parts[2:]))

        for vn in views:
            key = self._presence_key(project_id, vn)
            # 获取 score > cutoff 的成员（未过期）
            members = await self._redis.zrangebyscore(
                key, min=cutoff, max="+inf", withscores=True
            )
            for member, score in members:
                # member 格式: "user_id|user_name"
                parts = member.split("|", 1)
                uid = parts[0]
                uname = parts[1] if len(parts) > 1 else ""
                results.append({
                    "user_id": uid,
                    "user_name": uname,
                    "view_name": vn,
                    "last_heartbeat": score,
                })

        return results

    async def get_editing_states(
        self, project_id: UUID
    ) -> list[dict[str, Any]]:
        """获取当前编辑状态列表。

        Returns
        -------
        list[dict]
            编辑状态列表，每项含 user_id + 编辑详情
        """
        editing_key = self._editing_key(project_id)
        all_states = await self._redis.hgetall(editing_key)

        results: list[dict[str, Any]] = []
        for user_id_str, data_str in all_states.items():
            try:
                data = json.loads(data_str)
                results.append({"user_id": user_id_str, **data})
            except (json.JSONDecodeError, TypeError):
                continue

        return results

    async def remove_user(
        self, project_id: UUID, user_id: UUID, view_name: str
    ) -> None:
        """移除用户的在线状态和编辑状态。

        Parameters
        ----------
        project_id : UUID
            项目 ID
        user_id : UUID
            用户 ID
        view_name : str
            视图名称
        """
        key = self._presence_key(project_id, view_name)

        # 移除 ZSET 中该用户的所有条目（member 含 user_id| 前缀）
        # 需要扫描匹配
        pattern = f"{user_id}|*"
        members = await self._redis.zrangebyscore(key, "-inf", "+inf")
        for member in members:
            if member.startswith(f"{user_id}|"):
                await self._redis.zrem(key, member)

        # 移除编辑状态
        editing_key = self._editing_key(project_id)
        await self._redis.hdel(editing_key, str(user_id))

    async def cleanup_expired(self, project_id: UUID) -> int:
        """清理过期用户（心跳超过 60s 未更新）。

        Returns
        -------
        int
            清理的过期用户数
        """
        cutoff = time.time() - HEARTBEAT_EXPIRE_SECONDS
        cleaned = 0

        # 扫描所有视图
        pattern = f"presence:{project_id}:*"
        async for key in self._redis.scan_iter(match=pattern):
            # 获取过期成员（score < cutoff）
            expired_members = await self._redis.zrangebyscore(
                key, min="-inf", max=cutoff
            )
            if expired_members:
                # 移除过期成员
                await self._redis.zrem(key, *expired_members)
                cleaned += len(expired_members)

                # 同时清理编辑状态
                editing_key = self._editing_key(project_id)
                for member in expired_members:
                    uid = member.split("|", 1)[0]
                    await self._redis.hdel(editing_key, uid)

        return cleaned
