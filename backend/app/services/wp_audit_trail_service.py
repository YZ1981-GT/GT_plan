"""底稿审计轨迹扩展 — 审定数修改/程序标记/裁剪/预填充 写入 audit_log_entries 哈希链

Sprint 11 Task 11.7
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_logger_enhanced import audit_logger

logger = logging.getLogger(__name__)


class WpAuditTrailService:
    """底稿审计轨迹扩展服务"""

    # 底稿相关的审计动作类型
    ACTION_AUDITED_MODIFIED = "workpaper.audited_modified"
    ACTION_PROCEDURE_MARKED = "workpaper.procedure_marked"
    ACTION_PROCEDURE_TRIMMED = "workpaper.procedure_trimmed"
    ACTION_PREFILL_EXECUTED = "workpaper.prefill_executed"
    ACTION_CELL_EDITED = "workpaper.cell_edited"
    ACTION_FORMULA_CHANGED = "workpaper.formula_changed"

    @staticmethod
    async def log_audited_modification(
        *,
        user_id: uuid.UUID,
        wp_id: uuid.UUID,
        project_id: uuid.UUID,
        cell_ref: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
    ) -> None:
        """记录审定数修改"""
        await audit_logger.log_action(
            user_id=user_id,
            action=WpAuditTrailService.ACTION_AUDITED_MODIFIED,
            object_type="workpaper",
            object_id=wp_id,
            project_id=project_id,
            details={
                "cell_ref": cell_ref,
                "old_value": old_value,
                "new_value": new_value,
            },
        )

    @staticmethod
    async def log_procedure_mark(
        *,
        user_id: uuid.UUID,
        wp_id: uuid.UUID,
        project_id: uuid.UUID,
        procedure_id: str,
        mark_type: str,
    ) -> None:
        """记录程序标记（完成/不适用等）"""
        await audit_logger.log_action(
            user_id=user_id,
            action=WpAuditTrailService.ACTION_PROCEDURE_MARKED,
            object_type="workpaper",
            object_id=wp_id,
            project_id=project_id,
            details={
                "procedure_id": procedure_id,
                "mark_type": mark_type,
            },
        )

    # 程序裁剪恢复动作类型
    ACTION_PROCEDURE_TRIM_REVERTED = "workpaper.procedure_trim_reverted"

    @staticmethod
    async def log_procedure_trim(
        *,
        user_id: uuid.UUID,
        wp_id: uuid.UUID,
        project_id: uuid.UUID,
        trimmed_procedures: list[str],
        reason: str,
        action_type: str = "trim",
        reason_code: Optional[str] = None,
        reason_text: Optional[str] = None,
        batch_id: Optional[str] = None,
        sheet_key: Optional[str] = None,
    ) -> None:
        """记录程序裁剪/恢复操作。

        扩展 details 字段：action_type / row_ids / reason_code / reason_text / batch_id / user_id / timestamp
        revert 操作不删除历史 trim 日志条目（仅追加新 revert 条目）。
        """
        action = (
            WpAuditTrailService.ACTION_PROCEDURE_TRIMMED
            if action_type == "trim"
            else WpAuditTrailService.ACTION_PROCEDURE_TRIM_REVERTED
        )
        await audit_logger.log_action(
            user_id=user_id,
            action=action,
            object_type="workpaper",
            object_id=wp_id,
            project_id=project_id,
            details={
                "action_type": action_type,
                "trimmed_procedures": trimmed_procedures,
                "row_ids": trimmed_procedures,
                "reason": reason,
                "reason_code": reason_code,
                "reason_text": reason_text,
                "batch_id": batch_id,
                "sheet_key": sheet_key,
                "user_id": str(user_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    async def log_prefill(
        *,
        user_id: uuid.UUID,
        wp_id: uuid.UUID,
        project_id: uuid.UUID,
        cells_filled: int,
        source: str,
    ) -> None:
        """记录预填充执行"""
        await audit_logger.log_action(
            user_id=user_id,
            action=WpAuditTrailService.ACTION_PREFILL_EXECUTED,
            object_type="workpaper",
            object_id=wp_id,
            project_id=project_id,
            details={
                "cells_filled": cells_filled,
                "source": source,
            },
        )

    @staticmethod
    async def get_cell_history(
        db: AsyncSession,
        *,
        wp_id: uuid.UUID,
        cell_ref: str,
    ) -> list[dict]:
        """获取单元格级修改历史"""
        from sqlalchemy import select, text
        # Query audit_log_entries for this cell
        stmt = text("""
            SELECT id, action, user_id, details, created_at
            FROM audit_log_entries
            WHERE object_id = :wp_id
              AND action LIKE 'workpaper.%'
              AND details->>'cell_ref' = :cell_ref
            ORDER BY created_at DESC
            LIMIT 50
        """)
        try:
            result = await db.execute(stmt, {"wp_id": str(wp_id), "cell_ref": cell_ref})
            rows = result.fetchall()
            return [
                {
                    "id": str(r[0]),
                    "action": r[1],
                    "user_id": str(r[2]),
                    "details": r[3],
                    "created_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows
            ]
        except Exception:
            return []
