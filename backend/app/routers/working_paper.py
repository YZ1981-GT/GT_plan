"""底稿管理 API 路由

- GET    /api/projects/{id}/working-papers          — 底稿列表
- GET    /api/projects/{id}/working-papers/{wp_id}   — 底稿详情
- GET    /api/projects/{id}/working-papers/{wp_id}/download — 下载
- POST   /api/projects/{id}/working-papers/{wp_id}/upload   — 上传
- PUT    /api/projects/{id}/working-papers/{wp_id}/status   — 更新状态
- PUT    /api/projects/{id}/working-papers/{wp_id}/assign   — 分配
- POST   /api/projects/{id}/working-papers/{wp_id}/prefill  — 预填充
- POST   /api/projects/{id}/working-papers/{wp_id}/parse    — 解析回写
- GET    /api/projects/{id}/wp-index                 — 底稿索引列表
- GET    /api/projects/{id}/wp-cross-refs            — 交叉索引

Validates: Requirements 6.1-7.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.working_paper_service import WorkingPaperService
from app.services.prefill_service import PrefillService, ParseService
from app.models.workpaper_models import WpIndex, WpCrossRef, WorkingPaper, WpFileStatus

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UploadRequest(BaseModel):
    recorded_version: int


class StatusUpdateRequest(BaseModel):
    status: str


class AssignRequest(BaseModel):
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class ReviewStatusRequest(BaseModel):
    review_status: str


# ---------------------------------------------------------------------------
# Working paper endpoints
# ---------------------------------------------------------------------------

@router.get("/working-papers")
async def list_workpapers(
    project_id: UUID,
    audit_cycle: str | None = None,
    status: str | None = None,
    assigned_to: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿列表（支持筛选，需项目成员权限）"""
    svc = WorkingPaperService()
    return await svc.list_workpapers(
        db=db,
        project_id=project_id,
        audit_cycle=audit_cycle,
        status=status,
        assigned_to=assigned_to,
    )


@router.get("/working-papers/{wp_id}")
async def get_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿详情（需项目成员权限）"""
    svc = WorkingPaperService()
    detail = await svc.get_workpaper(db=db, wp_id=wp_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return detail


@router.get("/working-papers/{wp_id}/download")
async def download_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """下载底稿（需项目成员权限）"""
    svc = WorkingPaperService()
    try:
        return await svc.download_for_offline(db=db, wp_id=wp_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/working-papers/{wp_id}/upload")
async def upload_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: UploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """上传离线编辑的底稿"""
    svc = WorkingPaperService()
    try:
        result = await svc.upload_offline_edit(
            db=db, wp_id=wp_id, recorded_version=data.recorded_version,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/status")
async def update_status(
    project_id: UUID,
    wp_id: UUID,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """更新底稿编制生命周期状态

    编制状态流转由 WorkingPaperService.update_status 严格校验。
    提交复核请使用 POST /submit-review 专用端点（含4项门禁）。
    """
    svc = WorkingPaperService()
    try:
        result = await svc.update_status(db=db, wp_id=wp_id, new_status=data.status)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/assign")
async def assign_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """分配编制人/复核人（需 review 权限）"""
    svc = WorkingPaperService()
    try:
        result = await svc.assign_workpaper(
            db=db, wp_id=wp_id,
            assigned_to=data.assigned_to,
            reviewer=data.reviewer,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/submit-review")
async def submit_review(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """专用提交复核端点 — 统一校验 4 项门禁后流转复核状态

    门禁：1.复核人已分配 2.QC阻断=0 3.未解决批注=0 4.AI未确认=0
    全部通过后：
      - 编制状态 → under_review
      - 复核状态 → pending_level1
    """
    wp_result = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_id))
    wp = wp_result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 只有 edit_complete 或 revision_required→edit_complete 后才能提交
    if wp.status not in (WpFileStatus.edit_complete, WpFileStatus.draft):
        current_s = wp.status.value if wp.status else "unknown"
        raise HTTPException(
            status_code=400,
            detail=f"当前编制状态 {current_s} 不允许提交复核，需先完成编制（edit_complete）",
        )

    blocking_reasons = []

    # 门禁 1：复核人已分配
    if not wp.reviewer:
        blocking_reasons.append("复核人未分配")

    # 门禁 2：阻断级 QC 通过
    from app.models.workpaper_models import WpQcResult
    qc_result = await db.execute(
        sa.select(WpQcResult).where(WpQcResult.working_paper_id == wp_id)
        .order_by(WpQcResult.check_timestamp.desc()).limit(1)
    )
    qc = qc_result.scalar_one_or_none()
    if qc is None:
        blocking_reasons.append("未执行质量自检")
    elif qc.blocking_count > 0:
        blocking_reasons.append(f"存在 {qc.blocking_count} 个阻断级 QC 问题")

    # 门禁 3：无未解决复核意见
    try:
        from app.models.phase10_models import CellAnnotation
        ann_result = await db.execute(
            sa.select(sa.func.count()).select_from(CellAnnotation).where(
                CellAnnotation.project_id == project_id,
                CellAnnotation.object_type == "workpaper",
                CellAnnotation.object_id == wp_id,
                CellAnnotation.status != "resolved",
                CellAnnotation.is_deleted == sa.false(),
            )
        )
        unresolved = ann_result.scalar() or 0
        if unresolved > 0:
            blocking_reasons.append(f"{unresolved} 条未解决复核意见")
    except Exception:
        pass

    # 门禁 4：无未确认 AI 内容
    pd = wp.parsed_data or {}
    ai_items = pd.get("ai_content", [])
    unconfirmed_ai = [a for a in ai_items if a.get("status") == "pending"]
    if unconfirmed_ai:
        blocking_reasons.append(f"{len(unconfirmed_ai)} 项未确认的 AI 生成内容")

    if blocking_reasons:
        return {
            "status": "blocked",
            "blocking_reasons": blocking_reasons,
            "can_submit": False,
        }

    # 全部通过 → 流转复核状态
    svc = WorkingPaperService()
    try:
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status="pending_level1"
        )
        await db.commit()
        return {
            "status": "submitted",
            "can_submit": True,
            "blocking_reasons": [],
            "wp_status": result.get("status"),
            "review_status": result.get("review_status"),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/working-papers/{wp_id}/review-status")
async def update_review_status(
    project_id: UUID,
    wp_id: UUID,
    data: ReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """更新底稿复核任务状态（需 review 权限）

    复核人操作：
      pending_level1 → level1_in_progress → level1_passed/level1_rejected
      pending_level2 → level2_in_progress → level2_passed/level2_rejected
    """
    svc = WorkingPaperService()
    try:
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status=data.review_status
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/working-papers/{wp_id}/prefill")
async def prefill_workpaper(
    project_id: UUID,
    wp_id: UUID,
    year: int = 2025,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发预填充（需编辑权限）"""
    svc = PrefillService()
    result = await svc.prefill_workpaper(db=db, project_id=project_id, year=year, wp_id=wp_id)
    return result


@router.post("/working-papers/{wp_id}/parse")
async def parse_workpaper(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """手动触发解析回写（需编辑权限）"""
    svc = ParseService()
    result = await svc.parse_workpaper(db=db, project_id=project_id, wp_id=wp_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# WP Index & Cross-ref endpoints
# ---------------------------------------------------------------------------

@router.get("/wp-index")
async def list_wp_index(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿索引列表（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpIndex)
        .where(WpIndex.project_id == project_id, WpIndex.is_deleted == sa.false())
        .order_by(WpIndex.wp_code)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "wp_code": i.wp_code,
            "wp_name": i.wp_name,
            "audit_cycle": i.audit_cycle,
            "status": i.status.value if i.status else None,
            "assigned_to": str(i.assigned_to) if i.assigned_to else None,
            "reviewer": str(i.reviewer) if i.reviewer else None,
        }
        for i in items
    ]


@router.get("/wp-cross-refs")
async def list_wp_cross_refs(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """交叉索引关系（需项目成员权限）"""
    result = await db.execute(
        sa.select(WpCrossRef)
        .where(WpCrossRef.project_id == project_id)
        .order_by(WpCrossRef.created_at)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "source_wp_id": str(i.source_wp_id),
            "target_wp_code": i.target_wp_code,
            "cell_reference": i.cell_reference,
        }
        for i in items
    ]
