"""后台任务编排服务

Phase 12: 统一管理批量刷新/生成/提交/下载等长任务。
所有批量操作返回 job_id，前端通过 SSE 或轮询跟踪进度。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase12_models import BackgroundJob, BackgroundJobItem

logger = logging.getLogger(__name__)


class BackgroundJobService:
    """后台长任务编排"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self, project_id: UUID, job_type: str, wp_ids: list[UUID],
        payload: dict | None = None, user_id: UUID | None = None,
    ) -> dict:
        """创建任务 + 明细项，返回 job_id。"""
        job_id = uuid.uuid4()
        job = BackgroundJob(
            id=job_id, project_id=project_id, job_type=job_type,
            status="queued", payload=payload or {},
            progress_total=len(wp_ids), initiated_by=user_id,
        )
        self.db.add(job)

        for wid in wp_ids:
            item = BackgroundJobItem(
                id=uuid.uuid4(), job_id=job_id, wp_id=wid, status="queued",
            )
            self.db.add(item)

        await self.db.flush()
        logger.info("create_job: %s type=%s items=%d", job_id, job_type, len(wp_ids))
        return {"job_id": str(job_id), "status": "queued"}

    async def run_job(self, job_id: UUID, executor_fn=None) -> None:
        """执行任务：逐项处理，记录成功/失败。"""
        job = (await self.db.execute(
            sa.select(BackgroundJob).where(BackgroundJob.id == job_id)
        )).scalar_one_or_none()
        if not job:
            return

        job.status = "running"
        await self.db.flush()

        items = (await self.db.execute(
            sa.select(BackgroundJobItem).where(
                BackgroundJobItem.job_id == job_id,
                BackgroundJobItem.status == "queued",
            )
        )).scalars().all()

        for item in items:
            try:
                if executor_fn:
                    await executor_fn(item.wp_id)
                item.status = "succeeded"
                item.finished_at = datetime.now(timezone.utc)
                job.progress_done += 1
            except Exception as e:
                item.status = "failed"
                item.error_message = str(e)[:500]
                item.finished_at = datetime.now(timezone.utc)
                job.failed_count += 1
                logger.warning("job %s item %s failed: %s", job_id, item.wp_id, e)
            await self.db.flush()

        job.status = "succeeded" if job.failed_count == 0 else (
            "failed" if job.progress_done == 0 else "partial_failed"
        )
        job.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def retry_job(self, job_id: UUID, executor_fn=None) -> dict:
        """仅重试失败项。"""
        failed_items = (await self.db.execute(
            sa.select(BackgroundJobItem).where(
                BackgroundJobItem.job_id == job_id,
                BackgroundJobItem.status == "failed",
            )
        )).scalars().all()

        retried = 0
        for item in failed_items:
            item.status = "queued"
            item.error_message = None
            item.finished_at = None
            retried += 1
        await self.db.flush()

        if executor_fn:
            await self.run_job(job_id, executor_fn)

        return {"job_id": str(job_id), "retried_count": retried}

    async def get_job_status(self, job_id: UUID) -> dict | None:
        """获取任务状态 + 明细项。"""
        job = (await self.db.execute(
            sa.select(BackgroundJob).where(BackgroundJob.id == job_id)
        )).scalar_one_or_none()
        if not job:
            return None

        items = (await self.db.execute(
            sa.select(BackgroundJobItem).where(BackgroundJobItem.job_id == job_id)
        )).scalars().all()

        return {
            "id": str(job.id),
            "job_type": job.job_type,
            "status": job.status,
            "progress_total": job.progress_total,
            "progress_done": job.progress_done,
            "failed_count": job.failed_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "items": [
                {
                    "id": str(i.id), "wp_id": str(i.wp_id),
                    "status": i.status, "error_message": i.error_message,
                    "finished_at": i.finished_at.isoformat() if i.finished_at else None,
                }
                for i in items
            ],
        }
