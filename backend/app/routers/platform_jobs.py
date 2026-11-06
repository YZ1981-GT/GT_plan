"""通用 platform durable job 查询、取消与重试 API（B5）。

所有入口都带 project_id 且重走 ``require_project_access``；状态记录还要求当前用户是
任务 actor，避免项目成员通过 job id 探测他人请求载荷/结果。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.platform_job_models import PlatformJob
from app.services import platform_job_service as jobs

router = APIRouter(prefix="/api/projects/{project_id}/platform-jobs", tags=["platform-jobs"])


class RetryBody(BaseModel):
    """客户端生成的操作 id：网络重试必须复用，避免重复创建 retry job。"""

    operation_id: str = Field(..., min_length=1, max_length=100)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="任务不存在或无权访问")


async def _owned_job(
    db: AsyncSession,
    project_id: UUID,
    user: User,
    job_id: UUID,
    *,
    for_update: bool = False,
) -> PlatformJob:
    statement = sa.select(PlatformJob).where(
        PlatformJob.id == job_id,
        PlatformJob.project_id == project_id,
        PlatformJob.actor_id == user.id,
    )
    if for_update and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    job = (await db.execute(statement)).scalar_one_or_none()
    if job is None:
        raise _not_found()
    return job


@router.get("/{job_id}")
async def get_platform_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """权威恢复路径：SSE 断线、刷新和新标签页都从这条状态端点恢复。"""
    job = await _owned_job(db, project_id, user, job_id)
    return jobs.job_snapshot(job)


@router.post("/{job_id}/cancel")
async def cancel_platform_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """取消自己的 queued/running job；worker 在下一进度/阶段边界检查 fence。"""
    try:
        result = await jobs.request_cancel(
            db,
            project_id=project_id,
            actor_id=user.id,
            job_id=job_id,
        )
    except jobs.PlatformJobNotFound as exc:
        raise _not_found() from exc
    await db.commit()
    return result


@router.post("/{job_id}/retry")
async def retry_platform_job(
    project_id: UUID,
    job_id: UUID,
    body: RetryBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """失败/取消的 job 创建一个新逻辑运行，保留原 attempt 审计轨迹。"""
    old = await _owned_job(db, project_id, user, job_id, for_update=True)
    if old.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="只有失败或已取消的任务可以重试")
    key = f"retry:{old.id}:{jobs.canonical_hash({'operation_id': body.operation_id.strip()})}"
    try:
        new, _created = await jobs.create_or_get_job(
            db,
            operation=old.operation,
            project_id=project_id,
            actor_id=user.id,
            idempotency_key=key,
            payload_ref=dict(old.payload_ref or {}),
            progress_total=int(old.progress_total or 0),
            reserved_bytes=int(old.reserved_bytes or 0),
            max_attempts=int(old.max_attempts or 3),
        )
    except jobs.PlatformJobConflict as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return jobs.job_snapshot(new)
