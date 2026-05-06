"""批量简报路由 — Round 2 需求 6

POST /api/projects/briefs/batch
  body: {project_ids: UUID[], use_ai: bool}
  resp: {export_job_id} 异步，前端轮询

GET /api/projects/briefs/batch/{job_id}
  resp: 任务状态 + 结果

路由前缀规范：路由器内部带 /api 前缀，注册时不加额外前缀。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session
from app.deps import get_current_user
from app.models.core import User
from app.services.batch_brief_service import BatchBriefService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batch-brief"])


# ── Schemas ──

class BatchBriefRequest(BaseModel):
    project_ids: list[UUID] = Field(..., min_length=1, max_length=10)
    use_ai: bool = False


class BatchBriefResponse(BaseModel):
    export_job_id: str


# ── Background task ──

async def _run_batch_brief_task(
    job_id: UUID,
    project_ids: list[UUID],
    use_ai: bool,
    user_id: UUID,
) -> None:
    """后台执行批量简报生成"""
    async with async_session() as db:
        try:
            svc = BatchBriefService(db)
            await svc.execute_batch_brief(job_id, project_ids, use_ai, user_id)
            await db.commit()
            logger.info("批量简报任务完成: job_id=%s", job_id)
        except Exception as e:
            logger.error("批量简报任务失败: job_id=%s, error=%s", job_id, e)
            await db.rollback()
            # 标记任务失败
            try:
                from app.services.export_job_service import ExportJobService
                from app.models.phase13_models import ExportJobStatus
                job_svc = ExportJobService(db)
                job = await job_svc.get_job(job_id)
                if job:
                    job.status = ExportJobStatus.failed.value
                    await db.flush()
                    await db.commit()
            except Exception as inner_e:
                logger.error("标记任务失败时出错: %s", inner_e)


# ── Endpoints ──

@router.post("/api/projects/briefs/batch", response_model=BatchBriefResponse)
async def create_batch_brief(
    body: BatchBriefRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建批量简报异步任务

    - 接受多个 project_id，异步生成合并简报
    - 超过 6 个项目强制走后台任务
    - 7 天内相同项目组合复用缓存
    - AI 模式下额外调用 LLM 做全局总结，失败回退纯拼接
    """
    # 权限检查：只允许 manager/admin/partner
    allowed_roles = ("admin", "manager", "partner")
    if current_user.role.value not in allowed_roles:
        raise HTTPException(status_code=403, detail="权限不足：需要项目经理或管理员角色")

    svc = BatchBriefService(db)

    # 创建异步任务
    job_id = await svc.create_batch_brief_job(
        project_ids=body.project_ids,
        use_ai=body.use_ai,
        user_id=current_user.id,
    )
    await db.commit()

    # 检查是否命中缓存（已完成的 job 不需要后台执行）
    from app.services.export_job_service import ExportJobService
    from app.models.phase13_models import ExportJobStatus

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)

    if job and job.status != ExportJobStatus.succeeded.value:
        # 未命中缓存，启动后台任务
        background_tasks.add_task(
            _run_batch_brief_task,
            job_id=job_id,
            project_ids=body.project_ids,
            use_ai=body.use_ai,
            user_id=current_user.id,
        )

    return BatchBriefResponse(export_job_id=str(job_id))


@router.get("/api/projects/briefs/batch/{job_id}")
async def get_batch_brief_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """轮询批量简报任务状态

    返回:
        - status: queued/running/succeeded/failed/partial_failed
        - progress_total: 总项目数
        - progress_done: 已完成数
        - failed_count: 失败数
        - data: 成功时包含简报结果
    """
    svc = BatchBriefService(db)
    result = await svc.get_job_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result
