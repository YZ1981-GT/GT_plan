"""Spec C R10 Sprint 1.2 — 事件级联健康度聚合服务

聚合 4 个数据源（design D2/D3/D7）：
- outbox lag：MIN(created_at) of pending/processing events
- stuck handlers：status='processing' 且 30 分钟未更新
- DLQ depth：event_outbox_dlq.resolved_at IS NULL
- worker status：Redis worker_heartbeat:{name}（D1）

状态判定（design D2）：
- healthy: lag ≤ 60s AND dlq=0 AND 全部 worker alive
- degraded: lag > 60s OR dlq > 0 OR 1 个 worker miss OR Redis 不可用
- critical: lag > 300s OR worker miss > 1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 4 个 worker 名称（与 worker_helpers.write_heartbeat 调用方对齐）
_WORKER_NAMES = (
    "sla_worker",
    "import_recover_worker",
    "outbox_replay_worker",
    "import_worker",
)

# 阈值（design D2）
_LAG_DEGRADED_SECONDS = 60
_LAG_CRITICAL_SECONDS = 300
_STUCK_HANDLER_MINUTES = 30
_HEARTBEAT_STALE_SECONDS = 60


class EventCascadeHealthService:
    """事件级联健康度聚合 service。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_summary(self, project_id: UUID | None = None) -> dict:
        """聚合 4 数据源 + 状态判定。

        project_id 当前未用于过滤（outbox/dlq 不区分项目）；保留参数以备将来按项目隔离。
        """
        lag_seconds = await self._get_outbox_lag()
        stuck_handlers = await self._get_stuck_handlers()
        dlq_depth = await self._get_dlq_depth()
        worker_status, redis_available = await self._get_worker_status()

        status = self._compute_status(
            lag_seconds=lag_seconds,
            dlq_depth=dlq_depth,
            worker_status=worker_status,
            redis_available=redis_available,
        )

        return {
            "lag_seconds": lag_seconds,
            "stuck_handlers": stuck_handlers,
            "dlq_depth": dlq_depth,
            "worker_status": worker_status,
            "redis_available": redis_available,
            "status": status,
        }

    # ---------- 内部方法 ----------

    async def _get_outbox_lag(self) -> int:
        """outbox 待处理事件中最旧一条的 created_at 距今秒数。"""
        try:
            sql = sa_text(
                """
                SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at)))::INT AS lag
                FROM import_event_outbox
                WHERE status IN ('pending', 'processing')
                """
            )
            result = await self.db.execute(sql)
            value = result.scalar()
            return int(value) if value else 0
        except Exception as e:
            logger.debug("outbox lag query failed: %s", e)
            return 0

    async def _get_stuck_handlers(self) -> list[dict]:
        """processing 状态超过 30min 的事件（top 10）。"""
        try:
            sql = sa_text(
                f"""
                SELECT id::text AS outbox_id,
                       event_type,
                       EXTRACT(EPOCH FROM (now() - updated_at))::INT / 60 AS stuck_for_minutes
                FROM import_event_outbox
                WHERE status = 'processing'
                  AND updated_at < now() - INTERVAL '{_STUCK_HANDLER_MINUTES} minutes'
                ORDER BY updated_at ASC
                LIMIT 10
                """
            )
            result = await self.db.execute(sql)
            rows = result.mappings().all()
            return [
                {
                    "outbox_id": row["outbox_id"],
                    "event_type": row["event_type"],
                    "stuck_for_minutes": int(row["stuck_for_minutes"] or 0),
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug("stuck handlers query failed: %s", e)
            return []

    async def _get_dlq_depth(self) -> int:
        """死信队列中未解决的事件数。"""
        try:
            sql = sa_text(
                "SELECT COUNT(*) FROM event_outbox_dlq WHERE resolved_at IS NULL"
            )
            result = await self.db.execute(sql)
            value = result.scalar()
            return int(value) if value else 0
        except Exception as e:
            logger.debug("dlq depth query failed: %s", e)
            return 0

    async def _get_worker_status(self) -> tuple[dict, bool]:
        """读 Redis 4 个 worker 心跳，返回 (status_dict, redis_available)。"""
        try:
            from app.core.redis import redis_client
        except Exception:
            return {}, False

        if redis_client is None:
            return {}, False

        result: dict = {}
        try:
            now = datetime.now(timezone.utc)
            for name in _WORKER_NAMES:
                key = f"worker_heartbeat:{name}"
                raw = await redis_client.get(key)
                if not raw:
                    result[name] = {
                        "alive": False,
                        "last_heartbeat": None,
                        "stale_seconds": None,
                    }
                    continue
                try:
                    payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                    last_hb = datetime.fromisoformat(payload["last_heartbeat"])
                    if last_hb.tzinfo is None:
                        last_hb = last_hb.replace(tzinfo=timezone.utc)
                    stale = (now - last_hb).total_seconds()
                    result[name] = {
                        "alive": stale < _HEARTBEAT_STALE_SECONDS,
                        "last_heartbeat": payload["last_heartbeat"],
                        "stale_seconds": int(stale),
                    }
                except Exception:
                    result[name] = {
                        "alive": False,
                        "last_heartbeat": None,
                        "stale_seconds": None,
                    }
            return result, True
        except Exception as e:
            logger.warning("Redis unavailable for worker heartbeat: %s", e)
            return {}, False

    @staticmethod
    def _compute_status(
        *,
        lag_seconds: int,
        dlq_depth: int,
        worker_status: dict,
        redis_available: bool,
    ) -> str:
        """三档状态判定（含 Redis 不可用降级）。"""
        miss_count = sum(
            1 for w in worker_status.values() if not w.get("alive")
        )

        # critical: 严重故障
        if lag_seconds > _LAG_CRITICAL_SECONDS:
            return "critical"
        if miss_count > 1:
            return "critical"

        # degraded: 中度告警
        if lag_seconds > _LAG_DEGRADED_SECONDS:
            return "degraded"
        if dlq_depth > 0:
            return "degraded"
        if miss_count > 0:
            return "degraded"
        if not redis_available:
            return "degraded"

        return "healthy"
