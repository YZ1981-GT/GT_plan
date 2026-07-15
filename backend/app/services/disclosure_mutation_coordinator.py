"""附注 mutation 的轻量事务、幂等与提交后事件协调器。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventPayload

logger = logging.getLogger(__name__)

_LOCAL_TTL_SECONDS = 120
_LOCAL_RESULTS: dict[str, tuple[float, str, dict[str, Any]]] = {}
_LOCAL_LOCKS: dict[str, asyncio.Lock] = {}


def mutation_fingerprint(operation: str, payload: Any) -> str:
    """生成稳定请求摘要，用于拒绝 mutation_id 被不同请求复用。"""
    encoded = jsonable_encoder(payload)
    raw = json.dumps(
        {"operation": operation, "payload": encoded},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DisclosureMutationCoordinator:
    """保证 commit/rollback 边界，并仅在 commit 成功后发布事件。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        project_id: Any,
        mutation_id: str,
        fingerprint: str,
        ttl_seconds: int = _LOCAL_TTL_SECONDS,
    ) -> None:
        self.db = db
        self.project_id = str(project_id)
        self.mutation_id = mutation_id
        self.fingerprint = fingerprint
        self.ttl_seconds = ttl_seconds
        self.cache_key = f"disclosure:mutation:{self.project_id}:{mutation_id}"

    @staticmethod
    def _conflict() -> HTTPException:
        return HTTPException(
            status_code=409,
            detail={
                "error_code": "MUTATION_ID_CONFLICT",
                "message": "mutation_id 已用于不同的附注变更请求",
            },
        )

    def _read_local(self) -> dict[str, Any] | None:
        record = _LOCAL_RESULTS.get(self.cache_key)
        if record is None:
            return None
        expires_at, fingerprint, response = record
        if expires_at <= time.monotonic():
            _LOCAL_RESULTS.pop(self.cache_key, None)
            return None
        if fingerprint != self.fingerprint:
            raise self._conflict()
        return dict(response)

    async def _redis(self) -> Any | None:
        try:
            from app.core.redis import redis_client

            return redis_client
        except Exception as exc:  # pragma: no cover - import/environment degradation
            logger.warning("附注 mutation Redis 不可用，降级为进程内幂等: %s", exc)
            return None

    async def _read_redis(self) -> dict[str, Any] | None:
        client = await self._redis()
        if client is None:
            return None
        try:
            raw = await client.get(self.cache_key)
            if not raw:
                return None
            record = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if record.get("fingerprint") != self.fingerprint:
                raise self._conflict()
            if record.get("state") == "completed":
                return record.get("response")
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "MUTATION_IN_PROGRESS",
                    "message": "相同 mutation_id 的请求正在处理中，请稍后重试",
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("读取附注 mutation 幂等状态失败，继续执行: %s", exc)
            return None

    async def _claim_redis(self) -> bool:
        client = await self._redis()
        if client is None:
            return False
        record = json.dumps({"state": "processing", "fingerprint": self.fingerprint})
        try:
            claimed = await client.set(
                self.cache_key, record, ex=self.ttl_seconds, nx=True
            )
            if claimed:
                return True
            cached = await self._read_redis()
            if cached is not None:
                return False
            return False
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("声明附注 mutation 幂等键失败，降级继续执行: %s", exc)
            return False

    async def _store_completed(self, response: dict[str, Any]) -> None:
        _LOCAL_RESULTS[self.cache_key] = (
            time.monotonic() + self.ttl_seconds,
            self.fingerprint,
            dict(response),
        )
        client = await self._redis()
        if client is None:
            return
        record = json.dumps(
            {
                "state": "completed",
                "fingerprint": self.fingerprint,
                "response": response,
            },
            ensure_ascii=False,
        )
        try:
            await client.setex(self.cache_key, self.ttl_seconds, record)
        except Exception as exc:
            logger.warning("保存附注 mutation 幂等结果失败，已保留进程内结果: %s", exc)

    async def _release_claim(self, claimed: bool) -> None:
        if not claimed:
            return
        client = await self._redis()
        if client is None:
            return
        try:
            await client.delete(self.cache_key)
        except Exception as exc:
            logger.warning("清理失败的附注 mutation 幂等键失败: %s", exc)

    async def execute(
        self,
        mutate: Callable[[], Awaitable[dict[str, Any]]],
        event_factory: Callable[[dict[str, Any]], EventPayload],
    ) -> dict[str, Any]:
        """执行一次 mutation；重复请求返回缓存的同一最终响应。"""
        lock = _LOCAL_LOCKS.setdefault(self.cache_key, asyncio.Lock())
        async with lock:
            cached = self._read_local()
            if cached is not None:
                return cached
            cached = await self._read_redis()
            if cached is not None:
                _LOCAL_RESULTS[self.cache_key] = (
                    time.monotonic() + self.ttl_seconds,
                    self.fingerprint,
                    dict(cached),
                )
                return cached

            claimed = await self._claim_redis()
            # _claim_redis 可能发现其他 worker 已完成；再读一次进程内/Redis。
            cached = self._read_local()
            if cached is not None:
                return cached
            if not claimed:
                cached = await self._read_redis()
                if cached is not None:
                    return cached

            try:
                core_response = jsonable_encoder(await mutate())
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                await self._release_claim(claimed)
                raise

            warnings = list(core_response.get("warnings") or [])
            event_delivery = "published"
            payload = event_factory(core_response)
            payload.extra = {
                **(payload.extra or {}),
                "mutation_id": self.mutation_id,
                "project_id": self.project_id,
            }
            try:
                from app.services.event_bus import event_bus

                await event_bus.publish(payload)
            except Exception:
                event_delivery = "failed"
                logger.exception(
                    "附注 mutation 已提交但 EventBus 发布失败",
                    extra={
                        "project_id": self.project_id,
                        "mutation_id": self.mutation_id,
                        "event_type": payload.event_type.value,
                    },
                )
                warnings.append(
                    {
                        "code": "event_delivery_failed",
                        "message": "业务数据已保存，但事件通知发送失败",
                        "mutation_id": self.mutation_id,
                    }
                )

            response = {
                **core_response,
                "mutation_id": self.mutation_id,
                "committed": True,
                "event_delivery": event_delivery,
                "warnings": warnings,
            }
            await self._store_completed(response)
            return response
