"""归档编排 API — Refinement Round 1 需求 5

提供统一的归档编排入口，替代旧的三个分散端点。

端点：
  POST /api/projects/{project_id}/archive/orchestrate  — 启动归档编排
  GET  /api/projects/{project_id}/archive/jobs/{job_id} — 查询作业状态
  POST /api/projects/{project_id}/archive/jobs/{job_id}/retry — 重试失败作业
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.archive_orchestrator import ArchiveOrchestrator

router = APIRouter(
    prefix="/api/projects/{project_id}/archive",
    tags=["归档编排"],
)


class OrchestrateRequest(BaseModel):
    """归档编排请求体"""

    scope: str = Field(default="final", description="归档范围: final | interim")
    push_to_cloud: bool = Field(default=False, description="是否推送到云端")
    purge_local: bool = Field(default=False, description="是否清理本地数据")
    gate_eval_id: UUID | None = Field(
        default=None, description="门禁评估 ID（可选，用于跳过重复评估）"
    )


@router.post("/orchestrate")
async def orchestrate_archive(
    project_id: UUID,
    body: OrchestrateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动归档编排流程。

    串行执行 gate → wp_storage → push_to_cloud(可选) → purge_local(可选)。
    返回 ArchiveJob 状态，前端可轮询 jobs/{id} 获取进度。
    """
    orchestrator = ArchiveOrchestrator(db)
    job = await orchestrator.orchestrate(
        project_id=project_id,
        scope=body.scope,
        push_to_cloud=body.push_to_cloud,
        purge_local=body.purge_local,
        gate_eval_id=body.gate_eval_id,
        initiated_by=current_user.id,
    )
    await db.commit()
    return ArchiveOrchestrator._job_to_dict(job)


@router.get("/jobs/{job_id}")
async def get_archive_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询归档作业状态。"""
    orchestrator = ArchiveOrchestrator(db)
    result = await orchestrator.get_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="归档作业不存在")
    if result["project_id"] != str(project_id):
        raise HTTPException(status_code=404, detail="归档作业不属于该项目")
    return result


@router.post("/jobs/{job_id}/retry")
async def retry_archive_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败的归档作业（从断点续传）。"""
    orchestrator = ArchiveOrchestrator(db)
    try:
        job = await orchestrator.retry(
            job_id=job_id,
            initiated_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ArchiveOrchestrator._job_to_dict(job)
