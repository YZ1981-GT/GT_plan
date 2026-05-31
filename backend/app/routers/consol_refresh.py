"""合并模块一键级联刷新路由（consol-phase2-orchestration Task 2）

需求 2（A5）：
- `POST /api/consolidation/{project_id}/{year}/refresh-all` 入队后台 worker 返回 job_id
  （不在请求线程跑全量重算，R1）。
- `GET /api/consolidation/{project_id}/{year}/refresh-status/{job_id}` job 状态兜底查询
  （SSE 断开可查，EH6）。

SSE 进度复用既有 `GET /api/projects/{project_id}/events/stream`（events.py）——
worker 经 `event_bus.broadcast_raw("consol.refresh.progress", {...})` 推送，
前端在该 stream 上按 project_id/year 过滤后渲染进度条。SSE 不占 asyncpg pool（R5）。

router_registry 铁律：本 router 必须在 `router_registry/system.py` §6 合并报表组登记，
否则端点写好也 404。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_project_access
from app.models.core import User
from app.services.consol_refresh_job_service import get_job, schedule_refresh_job

router = APIRouter(prefix="/api/consolidation", tags=["合并一键刷新"])


@router.post("/{project_id}/{year}/refresh-all")
async def trigger_refresh_all(
    project_id: UUID,
    year: int,
    user: User = Depends(require_project_access("edit")),
):
    """一键级联刷新：入队后台 worker，立即返回 job_id（不在请求线程跑，R1）。

    worker 调 refresh_all(progress_cb=publish_sse) 跑完整 DAG（建树→worksheet→
    trial→对账→报表→附注），进度经 SSE 推到 `/api/projects/{project_id}/events/stream`。
    """
    job = schedule_refresh_job(project_id, year)
    return {
        "job_id": job.job_id,
        "project_id": job.project_id,
        "year": job.year,
        "status": job.status,
    }


@router.get("/{project_id}/{year}/refresh-status/{job_id}")
async def get_refresh_status(
    project_id: UUID,
    year: int,
    job_id: str,
    user: User = Depends(require_project_access("readonly")),
):
    """job 状态兜底查询（SSE 断开可查，EH6）。"""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="刷新任务不存在或已过期")
    return job.to_dict()
