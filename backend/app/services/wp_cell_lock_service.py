"""单元格级锁定服务 — 合伙人专属单元格标记，助理不可编辑

Sprint 11 Task 11.2 (Stub)

完整实现需要 Univer 的 CellPermission API 配合前端渲染。
此处提供后端锁定元数据管理。
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CellLockEntry:
    """单元格锁定条目"""
    def __init__(self, sheet_name: str, row: int, col: int, locked_by_role: str):
        self.sheet_name = sheet_name
        self.row = row
        self.col = col
        self.locked_by_role = locked_by_role


class WpCellLockService:
    """单元格级锁定管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_locked_cells(
        self,
        *,
        wp_id: uuid.UUID,
    ) -> list[dict]:
        """获取底稿中所有被锁定的单元格列表"""
        # Stub: 实际实现从 working_paper.parsed_data.locked_cells 读取
        return []

    async def lock_cell(
        self,
        *,
        wp_id: uuid.UUID,
        sheet_name: str,
        row: int,
        col: int,
        locked_by_role: str = "partner",
        user_id: uuid.UUID,
    ) -> dict:
        """锁定单元格（仅合伙人可操作）"""
        # Stub: 实际实现写入 working_paper.parsed_data.locked_cells
        logger.info(
            "Cell locked: wp=%s sheet=%s R%dC%d by role=%s",
            wp_id, sheet_name, row, col, locked_by_role,
        )
        return {
            "wp_id": str(wp_id),
            "sheet_name": sheet_name,
            "row": row,
            "col": col,
            "locked_by_role": locked_by_role,
        }

    async def unlock_cell(
        self,
        *,
        wp_id: uuid.UUID,
        sheet_name: str,
        row: int,
        col: int,
        user_id: uuid.UUID,
    ) -> dict:
        """解锁单元格"""
        logger.info("Cell unlocked: wp=%s sheet=%s R%dC%d", wp_id, sheet_name, row, col)
        return {"wp_id": str(wp_id), "unlocked": True}

    @staticmethod
    def can_edit_cell(
        user_role: str,
        locked_by_role: Optional[str],
    ) -> bool:
        """判断用户是否可编辑该单元格"""
        if not locked_by_role:
            return True
        # 只有同级或更高权限角色可编辑锁定单元格
        role_hierarchy = {"admin": 5, "partner": 4, "eqcr": 4, "qc": 3, "manager": 3, "auditor": 1}
        user_level = role_hierarchy.get(user_role, 0)
        lock_level = role_hierarchy.get(locked_by_role, 0)
        return user_level >= lock_level
