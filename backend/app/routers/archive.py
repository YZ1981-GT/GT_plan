"""归档编排 API — Refinement Round 1 需求 5

提供统一的归档编排入口（旧的三个分散归档端点已删除，spec attachment-archive-and-a-class-evidence ADR-AE-06）。

端点：
  POST /api/projects/{project_id}/archive/orchestrate            — 启动归档编排（归档管理权限 + 二次密码确认）
  GET  /api/projects/{project_id}/archive/jobs/{job_id}          — 查询作业状态（项目成员只读及以上）
  POST /api/projects/{project_id}/archive/jobs/{job_id}/retry    — 重试失败作业（归档管理权限 + 二次密码确认）
  GET  /api/projects/{project_id}/archive/jobs/{job_id}/package  — 下载归档包（项目成员只读及以上）
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_operation, require_project_access
from app.models.archive_models import ArchiveJob
from app.models.core import User
from app.routers.password_confirm import require_confirmation_token
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


async def _job_of_project(db: AsyncSession, project_id: UUID, job_id: UUID) -> ArchiveJob:
    job = (await db.execute(select(ArchiveJob).where(ArchiveJob.id == job_id))).scalar_one_or_none()
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="归档作业不存在")
    return job


@router.post("/orchestrate")
async def orchestrate_archive(
    project_id: UUID,
    body: OrchestrateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operation("archive:manage")),
    _token: None = Depends(require_confirmation_token),
):
    """启动归档编排（需二次密码确认）：gate → package → push_to_cloud? → lock → purge_local?。"""
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
    _user: User = Depends(require_project_access("readonly")),
):
    """查询归档作业状态。"""
    return ArchiveOrchestrator._job_to_dict(await _job_of_project(db, project_id, job_id))


@router.post("/jobs/{job_id}/retry")
async def retry_archive_job(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operation("archive:manage")),
    _token: None = Depends(require_confirmation_token),
):
    """重试失败的归档作业（从第一个未成功的步骤继续；与启动同级鉴权）。"""
    await _job_of_project(db, project_id, job_id)
    try:
        job = await ArchiveOrchestrator(db).retry(job_id=job_id, initiated_by=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ArchiveOrchestrator._job_to_dict(job)


@router.get("/jobs/{job_id}/package")
async def download_archive_package(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
):
    """下载归档包：作业须已成功；文件不在或 sha256 与完整性记录不符 ⇒ 409。"""
    from app.models.core import Project
    from app.models.phase16_models import EvidenceHashCheck
    from app.services.archive_package_builder import file_sha256

    job = await _job_of_project(db, project_id, job_id)
    if job.status != "succeeded":
        raise HTTPException(status_code=404, detail="归档作业未完成，暂无归档包")
    info = (job.section_progress or {}).get("package") or {}
    raw = info.get("path")
    path = Path(raw) if raw else None
    checks = (await db.execute(
        select(EvidenceHashCheck.sha256).where(EvidenceHashCheck.export_id == str(job.id),
                                               EvidenceHashCheck.file_path == raw)
    )).scalars().all() if raw else []
    if path is None or not path.is_file() or not checks or file_sha256(path) not in checks:
        raise HTTPException(status_code=409, detail="归档包文件不存在或与归档时的指纹不符，请重新归档")
    project = await db.get(Project, project_id)
    date = (job.finished_at or job.started_at).strftime("%Y%m%d") if (job.finished_at or job.started_at) else ""
    name = f"{(project.name if project else '项目')}-归档包-{date}.zip"
    ascii_name = name.encode("ascii", "ignore").decode() or "archive.zip"
    return FileResponse(
        path, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"},
    )
