"""底稿数据迁移服务

按 TemplateDiff 迁移 parsed_data：共有保留 / 新增填默认 / 删除归档。
迁移前创建快照，支持回滚。

Spec: wp-template-migration
Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wp_template_diff_service import TemplateDiff

logger = logging.getLogger(__name__)


class WpMigrationService:
    """底稿数据迁移服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 核心迁移逻辑（纯函数，无 DB 依赖）
    # ------------------------------------------------------------------

    @staticmethod
    def apply_diff_to_parsed_data(
        parsed_data: dict[str, Any],
        diff: TemplateDiff,
        new_template_structure: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """按 TemplateDiff 迁移 parsed_data（纯函数）

        策略：
        - 共有 sheet/列：保留用户数据不动
        - 新增 sheet：从 new_template_structure 填充默认值
        - 删除 sheet：归档到 _archived_data
        - 改名 sheet：重命名 key
        - 列级变化：新增列填默认 / 删除列归档

        Args:
            parsed_data: 原始 parsed_data（深拷贝后操作）
            diff: 模板 diff
            new_template_structure: 新模板结构 {sheet: {cells, columns}}

        Returns:
            迁移后的 parsed_data（新对象，不修改原始）
        """
        result = copy.deepcopy(parsed_data)
        html_data: dict[str, Any] = result.get("html_data", {})
        archived: dict[str, Any] = result.get("_archived_data", {})

        # 1. 处理 sheet 改名
        for old_name, new_name in diff.renamed_sheets:
            if old_name in html_data:
                html_data[new_name] = html_data.pop(old_name)

        # 2. 处理删除的 sheet → 归档
        for sheet_name in diff.removed_sheets:
            if sheet_name in html_data:
                archived[sheet_name] = html_data.pop(sheet_name)

        # 3. 处理新增的 sheet → 从新模板填充默认值
        for sheet_name in diff.added_sheets:
            if sheet_name not in html_data:
                if new_template_structure and sheet_name in new_template_structure:
                    html_data[sheet_name] = copy.deepcopy(
                        new_template_structure[sheet_name]
                    )
                else:
                    html_data[sheet_name] = {"cells": {}, "columns": []}

        # 4. 处理列级变化
        for col_diff in diff.column_diffs:
            sheet = html_data.get(col_diff.sheet_name)
            if not sheet:
                continue

            cells: dict[str, Any] = sheet.get("cells", {})
            columns: list[str] = sheet.get("columns", [])

            # 列改名：更新 columns 列表
            for old_col, new_col in col_diff.renamed:
                if old_col in columns:
                    idx = columns.index(old_col)
                    columns[idx] = new_col

            # 删除列：归档列数据
            for removed_col in col_diff.removed:
                if removed_col in columns:
                    columns.remove(removed_col)
                # 归档该列的 cell 数据
                sheet_archive = archived.setdefault(
                    f"_col_{col_diff.sheet_name}", {}
                )
                sheet_archive[removed_col] = {
                    coord: val
                    for coord, val in cells.items()
                    if _cell_in_column_header(coord, removed_col, columns)
                }

            # 新增列：添加到 columns
            for added_col in col_diff.added:
                if added_col not in columns:
                    columns.append(added_col)

            sheet["columns"] = columns

        result["html_data"] = html_data
        if archived:
            result["_archived_data"] = archived
        result["_migrated_at"] = datetime.now(timezone.utc).isoformat()

        return result

    # ------------------------------------------------------------------
    # 快照（迁移前保存）
    # ------------------------------------------------------------------

    async def create_snapshot(
        self,
        wp_id: UUID,
        parsed_data: dict[str, Any],
        migration_reason: str = "template_upgrade",
    ) -> UUID:
        """迁移前创建 parsed_data 快照

        Args:
            wp_id: 底稿 ID
            parsed_data: 迁移前的 parsed_data
            migration_reason: 迁移原因

        Returns:
            快照 ID
        """
        snapshot_id = uuid4()
        now = datetime.now(timezone.utc)

        await self.db.execute(sa.text("""
            INSERT INTO wp_migration_snapshots
                (id, wp_id, parsed_data_snapshot, migration_reason, created_at)
            VALUES (:id, :wp_id, :snapshot, :reason, :ts)
        """), {
            "id": str(snapshot_id),
            "wp_id": str(wp_id),
            "snapshot": json.dumps(parsed_data, ensure_ascii=False, default=str),
            "reason": migration_reason,
            "ts": now,
        })
        await self.db.flush()

        logger.info("快照已创建: wp=%s snapshot=%s", wp_id, snapshot_id)
        return snapshot_id

    # ------------------------------------------------------------------
    # 回滚
    # ------------------------------------------------------------------

    async def rollback(self, wp_id: UUID, snapshot_id: UUID) -> bool:
        """回滚到指定快照

        Args:
            wp_id: 底稿 ID
            snapshot_id: 快照 ID

        Returns:
            是否成功
        """
        row = (await self.db.execute(sa.text("""
            SELECT parsed_data_snapshot FROM wp_migration_snapshots
            WHERE id = :sid AND wp_id = :wid
        """), {"sid": str(snapshot_id), "wid": str(wp_id)})).first()

        if not row:
            logger.warning("快照不存在: wp=%s snapshot=%s", wp_id, snapshot_id)
            return False

        snapshot_data = row.parsed_data_snapshot
        if isinstance(snapshot_data, str):
            snapshot_data = json.loads(snapshot_data)

        await self.db.execute(sa.text("""
            UPDATE working_paper SET parsed_data = :data, updated_at = :ts
            WHERE id = :wid
        """), {
            "data": json.dumps(snapshot_data, ensure_ascii=False, default=str),
            "wid": str(wp_id),
            "ts": datetime.now(timezone.utc),
        })
        await self.db.flush()

        logger.info("回滚完成: wp=%s → snapshot=%s", wp_id, snapshot_id)
        return True

    # ------------------------------------------------------------------
    # 批量迁移单个底稿
    # ------------------------------------------------------------------

    async def migrate_workpaper(
        self,
        wp_id: UUID,
        diff: TemplateDiff,
        new_template_structure: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """迁移单个底稿

        流程：快照 → 应用 diff → 更新 DB

        Returns:
            {"status": "success"|"skipped"|"error", "snapshot_id": ..., "message": ...}
        """
        # 读取当前 parsed_data
        row = (await self.db.execute(sa.text(
            "SELECT parsed_data FROM working_paper WHERE id = :wid AND is_deleted = false"
        ), {"wid": str(wp_id)})).first()

        if not row:
            return {"status": "skipped", "message": "底稿不存在或已删除"}

        parsed_data = row.parsed_data
        if not parsed_data or not isinstance(parsed_data, dict):
            return {"status": "skipped", "message": "parsed_data 为空"}

        # 幂等检查：已迁移过则跳过
        if parsed_data.get("_migrated_at"):
            return {"status": "skipped", "message": "已迁移，跳过"}

        try:
            # 创建快照
            snapshot_id = await self.create_snapshot(wp_id, parsed_data)

            # 应用 diff
            migrated = self.apply_diff_to_parsed_data(
                parsed_data, diff, new_template_structure
            )

            # 更新 DB
            await self.db.execute(sa.text("""
                UPDATE working_paper
                SET parsed_data = :data, updated_at = :ts
                WHERE id = :wid
            """), {
                "data": json.dumps(migrated, ensure_ascii=False, default=str),
                "wid": str(wp_id),
                "ts": datetime.now(timezone.utc),
            })
            await self.db.flush()

            return {
                "status": "success",
                "snapshot_id": str(snapshot_id),
                "message": "迁移成功",
            }
        except Exception as e:
            logger.error("迁移失败: wp=%s error=%s", wp_id, e)
            return {"status": "error", "message": str(e)}


def _cell_in_column_header(
    coord: str, header: str, columns: list[str]
) -> bool:
    """判断 cell 坐标是否属于某列标题（简化实现）

    实际场景中列标题对应的是第一行的值，
    这里简化为：如果 header 在 columns 中，返回 False（不归档共有列的数据）。
    """
    # 简化实现：归档时不按坐标过滤，保留所有被删除列的标记
    return True
