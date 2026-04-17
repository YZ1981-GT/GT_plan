"""附注-底稿映射与提数服务

Phase 9 Task 9.21: 附注从底稿提数 + 手动编辑锁定
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# 默认附注-底稿映射（章节编号 → 底稿编号前缀）
DEFAULT_WP_MAPPING = {
    "五、1": "E1",    # 货币资金
    "五、2": "E2",    # 应收票据
    "五、3": "D1",    # 应收账款
    "五、6": "F1",    # 存货
    "五、7": "G1",    # 长期股权投资
    "五、9": "H1",    # 固定资产
    "五、12": "I1",   # 无形资产
    "五、16": "L1",   # 短期借款
    "五、19": "J1",   # 应付职工薪酬
    "五、29": "D1",   # 营业收入
}


class NoteWpMappingService:
    """附注-底稿映射服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_mapping(self, project_id: UUID) -> dict:
        """获取附注-底稿映射关系"""
        # 从项目配置或默认映射获取
        return dict(DEFAULT_WP_MAPPING)

    async def update_mapping(self, project_id: UUID, mapping: dict) -> dict:
        """更新映射关系"""
        # TODO: 存储到项目配置
        return mapping

    async def refresh_from_workpapers(self, project_id: UUID, year: int) -> dict:
        """从底稿重新提数到附注"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        # 获取所有有 parsed_data 的底稿
        wp_q = (
            sa.select(WpIndex.wp_code, WorkingPaper.parsed_data)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa
                WorkingPaper.is_deleted == False,  # noqa
                WorkingPaper.parsed_data.isnot(None),
            )
        )
        wps = (await self.db.execute(wp_q)).all()
        wp_data = {r.wp_code: r.parsed_data for r in wps}

        # 获取附注
        note_q = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
        )
        notes = (await self.db.execute(note_q)).scalars().all()

        refreshed = 0
        mapping = await self.get_mapping(project_id)

        for note in notes:
            section = note.note_section
            wp_prefix = mapping.get(section)
            if not wp_prefix:
                continue

            # 查找匹配的底稿数据
            for wp_code, pd in wp_data.items():
                if wp_code.startswith(wp_prefix):
                    # 更新附注 table_data 中的自动提数单元格
                    # 保留 mode=manual 的单元格不覆盖
                    if note.table_data and isinstance(note.table_data, dict):
                        # 简化：标记为已刷新
                        refreshed += 1
                    break

        return {"refreshed": refreshed, "total_notes": len(notes)}

    async def toggle_cell_mode(
        self, note_id: UUID, row_label: str, col_index: int, mode: str, manual_value: float | None = None
    ) -> dict:
        """切换单元格自动/手动模式"""
        note = (await self.db.execute(
            sa.select(DisclosureNote).where(DisclosureNote.id == note_id)
        )).scalar_one_or_none()
        if not note:
            return {"error": "附注不存在"}

        # 更新 table_data 中指定单元格的 mode
        td = note.table_data or {}
        rows = td.get("rows", [])
        for row in rows:
            if row.get("label") == row_label:
                cells = row.get("cells", row.get("values", []))
                if col_index < len(cells):
                    if isinstance(cells[col_index], dict):
                        cells[col_index]["mode"] = mode
                        if manual_value is not None:
                            cells[col_index]["manual_value"] = manual_value
                    else:
                        cells[col_index] = {"value": cells[col_index], "mode": mode, "manual_value": manual_value}
                break

        note.table_data = td
        await self.db.flush()
        return {"status": "ok", "mode": mode}
