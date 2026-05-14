"""事件级联监控服务 — 企业级联动 Sprint 4

提供：
1. 级联链路健康统计（成功率/平均耗时/失败数）
2. 告警阈值检查（成功率 < 95% 时告警）

Validates: Requirements 7.1, 7.2, 7.4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Alert threshold: success rate below this triggers alert
ALERT_THRESHOLD = 0.95  # 95%


class EventCascadeMonitor:
    """事件级联健康监控"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_stats(self, hours: int = 24) -> dict:
        """获取最近 N 小时的级联健康统计。

        Returns:
            {
                "total_count": int,
                "success_count": int,
                "failed_count": int,
                "degraded_count": int,
                "success_rate": float,  # 0.0 ~ 1.0
                "avg_duration_ms": float,
                "hours": int,
            }
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = text("""
            SELECT
                COUNT(*) AS total_count,
                COUNT(*) FILTER (WHERE status = 'completed') AS success_count,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
                COUNT(*) FILTER (WHERE status = 'degraded') AS degraded_count,
                COALESCE(AVG(total_duration_ms), 0) AS avg_duration_ms
            FROM event_cascade_log
            WHERE started_at >= :since
        """)

        try:
            result = await self.db.execute(query, {"since": since})
            row = result.fetchone()
        except Exception:
            # Fallback for SQLite (no FILTER syntax)
            query_fallback = text("""
                SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN status = 'degraded' THEN 1 ELSE 0 END) AS degraded_count,
                    COALESCE(AVG(total_duration_ms), 0) AS avg_duration_ms
                FROM event_cascade_log
                WHERE started_at >= :since
            """)
            result = await self.db.execute(query_fallback, {"since": since})
            row = result.fetchone()

        if not row or row[0] == 0:
            return {
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "degraded_count": 0,
                "success_rate": 1.0,
                "avg_duration_ms": 0.0,
                "hours": hours,
            }

        total = int(row[0])
        success = int(row[1] or 0)
        failed = int(row[2] or 0)
        degraded = int(row[3] or 0)
        avg_ms = float(row[4] or 0)

        success_rate = success / total if total > 0 else 1.0

        return {
            "total_count": total,
            "success_count": success,
            "failed_count": failed,
            "degraded_count": degraded,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": round(avg_ms, 2),
            "hours": hours,
        }

    async def check_alert_threshold(self) -> bool:
        """检查是否需要告警（成功率 < 95%）。

        Returns:
            True if success_rate < 95% (alert needed)
        """
        stats = await self.get_health_stats(hours=24)
        # Only alert if there are enough samples
        if stats["total_count"] < 5:
            return False
        return stats["success_rate"] < ALERT_THRESHOLD
