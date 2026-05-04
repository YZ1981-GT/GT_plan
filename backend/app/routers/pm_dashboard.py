"""项目经理视角 API — 待复核收件箱 / 批量复核 / 进度看板 / 进度简报 / 交叉引用 / 客户沟通"""

from __future__ import annotations

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bulk_operations import BulkResult
from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.pm_service import (
    ReviewInboxService,
    BatchReviewService,
    ProjectProgressService,
    ProgressBriefService,
    CrossRefCheckService,
    ClientCommunicationService,
)

router = APIRouter(tags=["pm-dashboard"])


# ── Schemas ──

class BatchReviewRequest(BaseModel):
    wp_ids: list[str]
    action: str  # "approve" | "reject"
    comment: str = ""


class CommunicationCreate(BaseModel):
    date: str = ""
    contact_person: str = ""
    topic: str = ""
    content: str = ""
    commitments: str = ""
    related_wp_codes: list[str] = []
    related_accounts: list[str] = []


# ── 1. 待复核收件箱（全局 + 项目级） ──

@router.get("/api/review-inbox")
async def get_global_review_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全局待复核收件箱 — 跨项目"""
    svc = ReviewInboxService(db)
    return await svc.get_inbox(current_user.id, page=page, page_size=page_size)


@router.get("/api/projects/{project_id}/review-inbox")
async def get_project_review_inbox(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """项目级待复核收件箱"""
    svc = ReviewInboxService(db)
    return await svc.get_inbox(current_user.id, project_id=project_id, page=page, page_size=page_size)


# ── 2. 批量复核 ──

@router.post("/api/projects/{project_id}/batch-review")
async def batch_review(
    project_id: UUID,
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
) -> BulkResult:
    """批量通过/退回底稿 — 返回统一 BulkResult 格式"""
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action 必须是 approve 或 reject")
    svc = BatchReviewService(db)
    raw = await svc.batch_review(
        project_id,
        [UUID(wid) for wid in body.wp_ids],
        body.action,
        current_user.id,
        body.comment,
    )
    await db.commit()

    # 将旧格式 succeeded/skipped 转为统一 BulkResult
    succeeded = raw.get("succeeded", [])
    skipped = raw.get("skipped", [])
    failed = [{"id": sid, "error": "状态不允许此操作"} for sid in skipped]
    total = len(succeeded) + len(skipped)
    return BulkResult(
        succeeded=succeeded,
        failed=failed,
        total=total,
        success_count=len(succeeded),
        fail_count=len(skipped),
    )


# ── 3. 项目进度看板 ──

@router.get("/api/projects/{project_id}/progress-board")
async def get_progress_board(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """项目底稿进度看板（按循环分组 + 看板列）"""
    svc = ProjectProgressService(db)
    return await svc.get_progress(project_id)


# ── 4. 进度简报 ──

@router.get("/api/projects/{project_id}/progress-brief")
async def get_progress_brief(
    project_id: UUID,
    polish: bool = Query(False, description="是否用 LLM 润色简报"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """生成项目进度简报（polish=true 时调用 LLM 润色）"""
    svc = ProgressBriefService(db)
    return await svc.generate_brief(project_id, polish_with_llm=polish)


# ── 5. 交叉引用检查 ──

@router.get("/api/projects/{project_id}/cross-ref-check")
async def check_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """检查底稿交叉引用完整性"""
    svc = CrossRefCheckService(db)
    return await svc.check_cross_refs(project_id)


# ── 6. 客户沟通记录 ──

@router.get("/api/projects/{project_id}/communications")
async def list_communications(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取客户沟通记录列表"""
    svc = ClientCommunicationService(db)
    return await svc.list_communications(project_id)


@router.post("/api/projects/{project_id}/communications")
async def add_communication(
    project_id: UUID,
    body: CommunicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """新增客户沟通记录"""
    svc = ClientCommunicationService(db)
    result = await svc.add_communication(project_id, current_user.id, body.model_dump())
    await db.commit()
    return result


@router.delete("/api/projects/{project_id}/communications/{comm_id}")
async def delete_communication(
    project_id: UUID,
    comm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """删除客户沟通记录"""
    svc = ClientCommunicationService(db)
    ok = await svc.delete_communication(project_id, comm_id)
    await db.commit()
    if not ok:
        raise HTTPException(404, "记录不存在")
    return {"message": "删除成功"}
