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
        """按审计循环分组统计完成度

        A 循环特殊处理：除了底稿级 status（整体 prepared/reviewed），还读取
        FieldOverrideService 中各 A 类程序表的程序项完成率（procedure-level），
        提供更细粒度的"完成与报告"阶段进度。
        """
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

        # A 循环程序级进度（从 FieldOverrideService 读 procedure_table:A* 的 status 字段）
        a_procedure_progress = await self._get_a_procedure_progress(project_id)

        return {
            "by_cycle": by_cycle,
            "total": total_all,
            "done": done_all,
            "rate": overall_rate,
            "a_procedure_progress": a_procedure_progress,
        }

    async def _get_a_procedure_progress(self, project_id: UUID) -> dict:
        """从 FieldOverrideService 读取 A 类程序表各项的完成状态，返回汇总进度。

        Returns: { total_items, completed_items, rate, by_wp: { A1: {total, completed}, ... } }
        """
        try:
            # 查所有 scope 以 procedure_table:A 开头的 field=status 的覆盖值
            stmt = sa.text("""
                SELECT scope, item_key, value
                FROM workpaper_field_overrides
                WHERE project_id = :pid
                  AND scope LIKE 'procedure_table:A%'
                  AND field = 'status'
            """)
            rows = (await self.db.execute(stmt, {"pid": str(project_id)})).all()

            by_wp: dict[str, dict] = {}
            total = 0
            completed = 0
            for r in rows:
                scope = r[0]  # 'procedure_table:A1'
                wp_code = scope.replace("procedure_table:", "")
                status_val = r[2]  # JSON value
                # value 可能是 JSON 字符串
                status = status_val if isinstance(status_val, str) else str(status_val or "")
                status = status.strip('"')

                if wp_code not in by_wp:
                    by_wp[wp_code] = {"total": 0, "completed": 0}
                by_wp[wp_code]["total"] += 1
                total += 1
                if status in ("completed", "not_applicable"):
                    by_wp[wp_code]["completed"] += 1
                    completed += 1

            rate = round(completed / total * 100, 1) if total > 0 else 0
            return {"total_items": total, "completed_items": completed, "rate": rate, "by_wp": by_wp}
        except Exception as e:
            logger.debug("A 循环程序级进度查询失败: %s", e)
            return {"total_items": 0, "completed_items": 0, "rate": 0, "by_wp": {}}

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
