"""底稿交叉索引与完成度服务

Phase 9 Task 9.7: 交叉索引自动建立 + 完成度统计 + 超期预警
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpCrossRef, WpIndex, WorkingPaper

logger = logging.getLogger(__name__)


class WpProgressService:
    """底稿完成度与交叉索引"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_progress(self, project_id: UUID) -> dict:
        """按审计循环分组统计完成度"""
        q = (
            sa.select(
                WpIndex.audit_cycle,
                WpIndex.status,
                sa.func.count(WpIndex.id).label("cnt"),
            )
            .where(WpIndex.project_id == project_id, WpIndex.is_deleted == False)  # noqa
            .group_by(WpIndex.audit_cycle, WpIndex.status)
        )
        rows = (await self.db.execute(q)).all()

        by_cycle: dict[str, dict] = {}
        for r in rows:
            cycle = r.audit_cycle or "OTHER"
            if cycle not in by_cycle:
                by_cycle[cycle] = {"total": 0, "not_started": 0, "in_progress": 0, "prepared": 0, "reviewed": 0, "archived": 0}
            by_cycle[cycle]["total"] += r.cnt
            status_key = r.status if r.status in by_cycle[cycle] else "not_started"
            by_cycle[cycle][status_key] = by_cycle[cycle].get(status_key, 0) + r.cnt

        total_all = sum(c["total"] for c in by_cycle.values())
        done_all = sum(c.get("prepared", 0) + c.get("reviewed", 0) + c.get("archived", 0) for c in by_cycle.values())
        overall_rate = round(done_all / total_all * 100, 1) if total_all > 0 else 0

        return {"by_cycle": by_cycle, "total": total_all, "done": done_all, "rate": overall_rate}

    async def get_overdue(self, project_id: UUID, days: int = 7) -> list[dict]:
        """超期底稿预警"""
        cutoff = date.today() - timedelta(days=days)
        q = (
            sa.select(
                WpIndex.id.label("wp_index_id"),
                WpIndex.wp_code,
                WpIndex.wp_name,
                WpIndex.audit_cycle,
                WpIndex.assigned_to,
                WpIndex.created_at,
                WorkingPaper.id.label("wp_id"),
            )
            .outerjoin(WorkingPaper, sa.and_(
                WorkingPaper.wp_index_id == WpIndex.id,
                WorkingPaper.is_deleted == False,  # noqa
            ))
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa
                WpIndex.status == "not_started",
                WpIndex.created_at <= cutoff,
            )
            .order_by(WpIndex.created_at)
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "wp_index_id": str(r.wp_index_id),
                "wp_id": str(r.wp_id) if r.wp_id else None,
                "wp_code": r.wp_code,
                "wp_name": r.wp_name,
                "audit_cycle": r.audit_cycle,
                "assigned_to": str(r.assigned_to) if r.assigned_to else None,
                "created_at": str(r.created_at),
                "overdue_days": (date.today() - r.created_at.date()).days if r.created_at else days,
            }
            for r in rows
        ]

    async def get_cross_refs(self, project_id: UUID) -> list[dict]:
        """获取底稿交叉引用关系（供力导向图可视化）"""
        q = (
            sa.select(WpCrossRef)
            .where(WpCrossRef.project_id == project_id)
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [
            {
                "source_wp_id": str(r.source_wp_id),
                "target_wp_code": r.target_wp_code,
                "cell_reference": r.cell_reference,
            }
            for r in rows
        ]
