"""底稿复核 + 分配 API 路由（从 working_paper.py 拆出，零行为变更）

复核/分配域端点（与 working_paper 主 router 共用 `/api/projects/{project_id}` 前缀）：
- PUT    /working-papers/{wp_id}/assign         — 分配编制人/复核人
- POST   /working-papers/{wp_id}/submit-review   — 提交复核（5 项门禁）
- PUT    /working-papers/{wp_id}/review-status    — 更新复核任务状态

私有 helper `_send_reassignment_notifications` 随其唯一调用方 `assign_workpaper` 同模块迁移。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access, check_consol_lock
from app.models.core import User
from app.services.working_paper_service import WorkingPaperService
from app.models.workpaper_models import WpIndex, WorkingPaper

# 共享请求模型从 schemas 引入（避免反向依赖主 router）
from app.schemas.workpaper_requests import (
    AssignRequest,
    ReviewStatusRequest,
)

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ---------------------------------------------------------------------------
# 重新分配通知辅助函数
# ---------------------------------------------------------------------------


async def _send_reassignment_notifications(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    old_assignee_id: UUID,
    new_assignee_id: UUID,
) -> None:
    """重新分配底稿后，通知原编制人和新编制人。

    - 原编制人收到"底稿 {wp_code} 已被重新分配"
    - 新编制人收到"项目「{project_name}」的底稿 {wp_code} 已转交给您"
    """
    import logging
    from app.services.notification_service import NotificationService
    from app.services.notification_types import ASSIGNMENT_CREATED, WORKPAPER_REMINDER
    from app.models.core import Project

    logger = logging.getLogger(__name__)
    notif_svc = NotificationService(db)

    # 获取底稿编号（wp_code）
    wp_row = (await db.execute(
        sa.select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()

    wp_code = "未知底稿"
    if wp_row:
        idx_row = (await db.execute(
            sa.select(WpIndex.wp_code).where(WpIndex.id == wp_row)
        )).scalar_one_or_none()
        if idx_row:
            wp_code = idx_row

    # 获取项目名称
    project_name = (await db.execute(
        sa.select(Project.name).where(Project.id == project_id)
    )).scalar_one_or_none() or "未知项目"

    # 通知原编制人："底稿 {wp_code} 已被重新分配"
    await notif_svc.send_notification(
        user_id=old_assignee_id,
        notification_type=WORKPAPER_REMINDER,
        title="底稿已被重新分配",
        content=f"底稿 {wp_code} 已被重新分配给其他人员",
        metadata={
            "object_type": "working_paper",
            "object_id": str(wp_id),
            "project_id": str(project_id),
        },
    )

    # 通知新编制人："项目「{project_name}」的底稿 {wp_code} 已转交给您"
    await notif_svc.send_notification(
        user_id=new_assignee_id,
        notification_type=ASSIGNMENT_CREATED,
        title="底稿已转交给您",
        content=f"项目「{project_name}」的底稿 {wp_code} 已转交给您，请及时处理",
        metadata={
            "object_type": "working_paper",
            "object_id": str(wp_id),
            "project_id": str(project_id),
        },
    )

    logger.info(
        "[REASSIGN] wp=%s old=%s new=%s project=%s",
        wp_id, old_assignee_id, new_assignee_id, project_id,
    )


@router.put("/working-papers/{wp_id}/assign")
async def assign_workpaper(
    project_id: UUID,
    wp_id: UUID,
    data: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
    _lock_check=Depends(check_consol_lock),
):
    """分配编制人/复核人（需 review 权限）

    重新分配时发送通知：
    - 原编制人收到"底稿已被重新分配"
    - 新编制人收到"项目 X 底稿 Y 已转交给您"
    """
    svc = WorkingPaperService()

    # 改编制人 = 底稿主编委派，与 PUT /workpaper-leads 一样只给项目委派人（经理 / 合伙人 / admin）；
    # 只改复核人仍按 review 权限（spec procedure-trim-generation-delegation-chain 任务 12）
    if data.assigned_to is not None:
        from app.services.procedure_authorization import ensure_project_delegator

        await ensure_project_delegator(db, current_user, project_id)

    # ── 记录原编制人（用于重新分配通知） ──
    old_assigned_to: UUID | None = None
    if data.assigned_to is not None:
        wp_row = (await db.execute(
            sa.select(WorkingPaper.assigned_to).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )).scalar_one_or_none()
        old_assigned_to = wp_row  # 可能为 None（首次分配）

    from app.services.wp_visibility.delegation_guard import DelegationError

    try:
        result = await svc.assign_workpaper(
            db=db, wp_id=wp_id, project_id=project_id,
            assigned_to=data.assigned_to,
            reviewer=data.reviewer,
            actor_user_id=current_user.id,
            expand_scope=data.expand_scope,
            scope_reason=data.scope_reason,
        )
        await db.commit()
    except DelegationError as e:
        # 编制人走底稿主编委派事务：已裁 / 在回收站 409，被委派人看不到该循环 400（带理由 expand_scope 重试）
        await db.rollback()
        raise HTTPException(status_code=e.http_status, detail=e.http_detail()) from e
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    # ── 重新分配通知（仅当 assigned_to 变更且原编制人存在时；新编制人用解析出的用户 id，入参可能是人员 id） ──
    new_assigned_to = UUID(result["assigned_to"]) if result.get("assigned_to") else None
    if (
        data.assigned_to is not None
        and old_assigned_to is not None
        and new_assigned_to is not None
        and old_assigned_to != new_assigned_to
    ):
        try:
            await _send_reassignment_notifications(
                db=db,
                project_id=project_id,
                wp_id=wp_id,
                old_assignee_id=old_assigned_to,
                new_assignee_id=new_assigned_to,
            )
            await db.commit()
        except Exception as e:
            # 通知发送失败不阻断主流程
            import logging as _logging
            _logging.getLogger(__name__).warning("发送底稿改派通知失败 wp=%s: %s", wp_id, e)

    return result


@router.post("/working-papers/{wp_id}/submit-review")
async def submit_review(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """提交复核；单笔和批量入口共用同一服务与门禁。"""
    from app.services.workpaper_review_submission_service import (
        ReviewSubmissionUnavailable,
        WorkpaperReviewSubmissionService,
    )

    try:
        result = await WorkpaperReviewSubmissionService().submit(
            db, project_id=project_id, wp_id=wp_id, actor_id=current_user.id,
        )
        await db.commit()
        return result.as_dict()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ReviewSubmissionUnavailable as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise


@router.put("/working-papers/{wp_id}/review-status")
async def update_review_status(
    project_id: UUID,
    wp_id: UUID,
    data: ReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
    _lock_check=Depends(check_consol_lock),
):
    """更新底稿复核任务状态（需 review 权限）

    复核人操作：
      pending_level1 → level1_in_progress → level1_passed/level1_rejected
      pending_level2 → level2_in_progress → level2_passed/level2_rejected
    """
    svc = WorkingPaperService()
    from app.services.workpaper_review_submission_service import assert_review_level_actor

    try:
        await assert_review_level_actor(
            db, project_id=project_id, wp_id=wp_id,
            new_review_status=data.review_status, actor=current_user,
        )
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status=data.review_status,
            project_id=project_id, reason=data.reason,
            rejected_by_id=current_user.id,
        )
        await db.commit()
        return result
    except LookupError as e:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
