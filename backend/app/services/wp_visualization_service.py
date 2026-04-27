"""数据提取可视化服务

Phase 12 P2-6: 公式高亮、来源追溯、差异对比。
从 parsed_data.formula_cells 缓存读取，不实时解析 Excel。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)


class WpVisualizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_formula_cells(self, wp_id: UUID) -> list[dict]:
        wp = (await self.db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if not wp:
            return []
        pd = wp.parsed_data or {}
        return pd.get("formula_cells", [])

    async def get_cell_data_source(self, wp_id: UUID, cell_ref: str) -> dict | None:
        cells = await self.get_formula_cells(wp_id)
        for c in cells:
            if c.get("cell_ref") == cell_ref:
                return {
                    "cell_ref": cell_ref,
                    "formula": c.get("formula", ""),
                    "formula_type": c.get("formula_type", ""),
                    "current_value": c.get("value"),
                    "source_table": c.get("source_table", "unknown"),
                }
        return None

    async def compare_refresh_diff(self, wp_id: UUID, before: dict, after: dict) -> list[dict]:
        changes = []
        for key in set(list(before.keys()) + list(after.keys())):
            old_v = before.get(key)
            new_v = after.get(key)
            if old_v != new_v:
                try:
                    rate = round((float(new_v or 0) - float(old_v or 0)) / float(old_v) * 100, 1) if old_v else None
                except (ValueError, ZeroDivisionError):
                    rate = None
                changes.append({"cell_ref": key, "old_value": old_v, "new_value": new_v, "change_rate": rate})
        return changes
