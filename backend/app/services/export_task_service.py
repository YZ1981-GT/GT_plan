"""Word 导出任务服务 — 状态机 + 版本管理

功能：
- create_task: 创建导出任务 + 初始版本
- get_task: 获取任务详情
- update_status: 状态机转换校验
- confirm_task: 人工确认
- get_history: 项目导出历史
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import (
    VALID_STATUS_TRANSITIONS,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)

logger = logging.getLogger(__name__)


class ExportTaskService:
    """Word 导出状态机与版本管理"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(
        self,
        project_id: UUID,
        doc_type: str,
        template_type: str | None,
        user_id: UUID,
    ) -> WordExportTask:
        """创建 word_export_task + 初始版本 v1"""
        task = WordExportTask(
            project_id=project_id,
            doc_type=doc_type,
            status=WordExportStatus.draft.value,
            template_type=template_type,
            created_by=user_id,
        )
        self.db.add(task)
        await self.db.flush()

        # 创建初始版本
        version = WordExportTaskVersion(
            word_export_task_id=task.id,
            version_no=1,
            created_by=user_id,
        )
        self.db.add(version)
        await self.db.flush()

        logger.info("创建Word导出任务: task_id=%s, doc_type=%s", task.id, doc_type)
        return task

    async def get_task(self, task_id: UUID) -> WordExportTask | None:
        """获取任务详情"""
        result = await self.db.execute(
            sa.select(WordExportTask).where(WordExportTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, task_id: UUID, new_status: str) -> WordExportTask:
        """校验状态机转换并更新状态

        状态机：draft→generating→generated→editing→confirmed→signed
        confirmed 可 reopen 回 editing
        """
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"导出任务不存在: {task_id}")

        current = task.status
        allowed = VALID_STATUS_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise ValueError(
                f"非法状态转换: {current} → {new_status}，"
                f"允许的转换: {allowed}"
            )

        task.status = new_status
        await self.db.flush()
        logger.info("导出任务状态更新: %s → %s (task_id=%s)", current, new_status, task_id)
        return task

    async def confirm_task(self, task_id: UUID, user_id: UUID) -> WordExportTask:
        """人工确认导出任务

        仅 editing 状态可确认，设置 confirmed_by/confirmed_at
        """
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"导出任务不存在: {task_id}")

        if task.status != WordExportStatus.editing.value:
            raise ValueError(
                f"仅 editing 状态可确认，当前状态: {task.status}"
            )

        task.status = WordExportStatus.confirmed.value
        task.confirmed_by = user_id
        task.confirmed_at = datetime.utcnow()
        await self.db.flush()
        logger.info("导出任务已确认: task_id=%s, confirmed_by=%s", task_id, user_id)
        return task

    async def get_history(
        self, project_id: UUID
    ) -> list[WordExportTask]:
        """获取项目所有导出任务，按创建时间倒序"""
        result = await self.db.execute(
            sa.select(WordExportTask)
            .where(WordExportTask.project_id == project_id)
            .order_by(WordExportTask.created_at.desc())
        )
        return list(result.scalars().all())
