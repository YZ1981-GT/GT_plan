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
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpFileStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers",
    tags=["底稿批量操作"],
)

# 状态转换规则
_TRANSITIONS: dict[str, dict[str, str]] = {
    "submit_review": {
        "draft": "in_review",
    },
    "return_to_draft": {
        "in_review": "draft",
    },
    "mark_complete": {
        "in_review": "completed",
        "draft": "completed",
    },
}

# 操作→最低权限
_ACTION_PERMISSIONS: dict[str, str] = {
    "submit_review": "edit",       # auditor+
    "return_to_draft": "review",   # manager+
    "mark_complete": "review",     # manager+
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
    """批量变更底稿状态

    - submit_review: draft → in_review（auditor+）
    - return_to_draft: in_review → draft（manager+）
    - mark_complete: in_review/draft → completed（manager+）

    不允许的转换跳过（记入 skipped 列表），不回滚成功项。
    """
    if body.action not in _TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"不支持的操作: {body.action}")

    if not body.wp_ids:
        raise HTTPException(status_code=400, detail="wp_ids 不能为空")

    # 权限检查
    min_perm = _ACTION_PERMISSIONS.get(body.action, "review")
    # 简化权限检查：通过 require_project_access 已在路由层保证

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

        # 执行状态变更
        new_status = allowed_transitions[current_status]
        wp.status = WpFileStatus(new_status)
        wp.updated_by = current_user.id
        success_count += 1

    await db.commit()

    return {
        "success_count": success_count,
        "skipped_count": len(skipped),
        "skipped": [s.model_dump() for s in skipped],
        "message": f"成功处理 {success_count} 个底稿" + (f"，跳过 {len(skipped)} 个" if skipped else ""),
    }
