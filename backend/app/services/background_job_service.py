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
