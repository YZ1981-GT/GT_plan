"""导出后台任务编排 — Phase 13 Stage 2.5

管理长时间运行的导出任务（全套导出、批量渲染、失败重试）。
统一走 job_id，支持页面刷新恢复与失败项重试。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import (
    ExportJob,
    ExportJobItem,
    ExportJobStatus,
)

logger = logging.getLogger(__name__)


class ExportJobService:
    """后台导出任务编排服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        project_id: UUID,
        job_type: str,
        payload: dict | None,
        user_id: UUID,
        total: int = 0,
    ) -> ExportJob:
        """创建后台导出任务

        Args:
            project_id: 项目ID
            job_type: 任务类型 (generate/full_package/retry)
            payload: 任务参数 (JSONB)
            user_id: 发起人ID
            total: 预计总项数
        """
        job = ExportJob(
            project_id=project_id,
            job_type=job_type,
            status=ExportJobStatus.queued.value,
            payload=payload or {},
            progress_total=total,
            progress_done=0,
            failed_count=0,
            initiated_by=user_id,
        )
        self.db.add(job)
        await self.db.flush()

        logger.info(
            "创建导出任务: job_id=%s, type=%s, project=%s",
            job.id, job_type, project_id,
        )
        return job

    async def get_job(self, job_id: UUID) -> ExportJob | None:
        """获取任务详情（含明细项）"""
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job_items(self, job_id: UUID) -> list[ExportJobItem]:
        """获取任务明细项列表"""
        result = await self.db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == job_id)
            .order_by(ExportJobItem.finished_at.asc().nullsfirst())
        )
        return list(result.scalars().all())

    async def add_item(
        self,
        job_id: UUID,
        word_export_task_id: UUID | None = None,
    ) -> ExportJobItem:
        """添加任务明细项"""
        item = ExportJobItem(
            job_id=job_id,
            word_export_task_id=word_export_task_id,
            status=ExportJobStatus.queued.value,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def update_item_status(
        self,
        item_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> ExportJobItem | None:
        """更新明细项状态"""
        result = await self.db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None

        item.status = status
        if error_message:
            item.error_message = error_message
        if status in (
            ExportJobStatus.succeeded.value,
            ExportJobStatus.failed.value,
        ):
            item.finished_at = datetime.utcnow()
        await self.db.flush()
        return item

    async def update_progress(
        self,
        job_id: UUID,
        done: int,
        failed: int = 0,
    ) -> ExportJob | None:
        """更新任务进度

        Args:
            job_id: 任务ID
            done: 已完成数
            failed: 失败数
        """
        result = await self.db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        job.progress_done = done
        job.failed_count = failed

        # Auto-determine job status
        if done + failed >= job.progress_total and job.progress_total > 0:
            if failed == 0:
                job.status = ExportJobStatus.succeeded.value
            elif done > 0:
                job.status = ExportJobStatus.partial_failed.value
            else:
                job.status = ExportJobStatus.failed.value

            # ── Phase 16: 导出完成后自动生成取证包 hash ──
            if job.status == ExportJobStatus.succeeded.value:
                try:
                    from app.services.export_integrity_service import export_integrity_service
                    from pathlib import Path
                    import glob
                    # 查找导出文件
                    export_dir = Path("storage") / "exports" / str(job_id)
                    if export_dir.exists():
                        files = [str(f) for f in export_dir.rglob("*") if f.is_file()]
                        if files:
                            manifest = await export_integrity_service.build_manifest(str(job_id), files)
                            await export_integrity_service.persist_checks(self.db, str(job_id), manifest["files"])
                            logger.info(f"[INTEGRITY] export hash generated: job={job_id} files={len(files)}")
                except Exception as _int_err:
                    logger.warning(f"[INTEGRITY] export hash generation failed: {_int_err}")

        elif done > 0 or failed > 0:
            job.status = ExportJobStatus.running.value

        await self.db.flush()
        logger.info(
            "导出任务进度: job_id=%s, done=%d/%d, failed=%d",
            job_id, done, job.progress_total, failed,
        )
        return job

    async def retry_failed(self, job_id: UUID) -> int:
        """重试失败项

        Only retries items with status='failed'. Returns count of retried items.
        """
        result = await self.db.execute(
            sa.select(ExportJobItem).where(
                ExportJobItem.job_id == job_id,
                ExportJobItem.status == ExportJobStatus.failed.value,
            )
        )
        failed_items = result.scalars().all()

        retried = 0
        for item in failed_items:
            item.status = ExportJobStatus.queued.value
            item.error_message = None
            item.finished_at = None
            retried += 1

        if retried > 0:
            # Reset job status to running
            job_result = await self.db.execute(
                sa.select(ExportJob).where(ExportJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job:
                job.status = ExportJobStatus.running.value
                job.failed_count = 0
                job.progress_done = max(0, job.progress_done - retried)
            await self.db.flush()

        logger.info("重试失败项: job_id=%s, retried=%d", job_id, retried)
        return retried
