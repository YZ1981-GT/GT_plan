"""底稿批量状态变更 API — Phase 2 F3

POST /api/projects/{project_id}/working-papers/batch-status

支持：批量提交复核 / 批量退回修改 / 批量标记完成
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers",
    tags=["底稿批量操作"],
)

# 兼容的编制生命周期动作；提交复核已迁到 /working-papers/batch-submit。
_TRANSITIONS: dict[str, dict[str, str]] = {
    "return_to_draft": {
        "edit_complete": "draft",
    },
    "mark_complete": {
        "draft": "edit_complete",
        "revision_required": "edit_complete",
    },
}

_ACTION_PERMISSIONS: dict[str, str] = {
    "return_to_draft": "edit",
    "mark_complete": "edit",
}


class BatchStatusRequest(BaseModel):
    wp_ids: list[UUID]
    action: str  # submit_review / return_to_draft / mark_complete
    comment: str | None = None


class SkippedItem(BaseModel):
    wp_id: str
    reason: str


@router.post("/batch-status")
async def batch_status_change(
    project_id: UUID,
    body: BatchStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """兼容的批量编制状态操作；提交复核必须走统一门禁入口。"""
    if body.action == "submit_review":
        raise HTTPException(
            status_code=410,
            detail={
                "code": "LEGACY_BATCH_REVIEW_RETIRED",
                "message": "旧批量提交入口已退役，请刷新页面后重试",
                "replacement": f"/api/projects/{project_id}/working-papers/batch-submit",
            },
        )
    if body.action not in _TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"不支持的操作: {body.action}")

    if not body.wp_ids:
        raise HTTPException(status_code=400, detail="wp_ids 不能为空")

    # 操作级项目权限；路径里有 project_id 不等于已隔离。
    min_perm = _ACTION_PERMISSIONS[body.action]
    await assert_project_permission(db, current_user, project_id, min_perm)

    allowed_transitions = _TRANSITIONS[body.action]
    success_count = 0
    skipped: list[SkippedItem] = []

    # 查询所有目标底稿
    result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id.in_(body.wp_ids),
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    workpapers = result.scalars().all()

    # 构建 ID→WP 映射
    wp_map = {wp.id: wp for wp in workpapers}

    for wp_id in body.wp_ids:
        wp = wp_map.get(wp_id)
        if not wp:
            skipped.append(SkippedItem(wp_id=str(wp_id), reason="底稿不存在或已删除"))
            continue

        current_status = wp.status.value if hasattr(wp.status, 'value') else str(wp.status)
        if current_status not in allowed_transitions:
            skipped.append(SkippedItem(
                wp_id=str(wp_id),
                reason=f"当前状态 '{current_status}' 不允许执行 '{body.action}'"
            ))
            continue

        # ── 版本链：状态变更前自动快照 ──
        new_status = allowed_transitions[current_status]
        await VersionTrailService.create_snapshot_fire_and_forget(
            db=db,
            project_id=project_id,
            workpaper_id=wp_id,
            user_id=current_user.id,
            snapshot_type="status_change",
            description=f"状态变更: {current_status} → {new_status}",
        )

        # 执行状态变更：复用单笔状态机（含退回修改完成后 review_status 归一）。
        from app.services.working_paper_service import WorkingPaperService

        await WorkingPaperService().update_status(
            db=db, wp_id=wp_id, new_status=new_status, project_id=project_id,
        )
        wp.updated_by = current_user.id
        success_count += 1

    await db.commit()

    return {
        "success_count": success_count,
        "skipped_count": len(skipped),
        "skipped": [s.model_dump() for s in skipped],
        "message": f"成功处理 {success_count} 个底稿" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
    }
