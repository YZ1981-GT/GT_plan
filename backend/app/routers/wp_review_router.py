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
from app.models.ai_models import AIConfirmationStatus, AIContent
from app.models.core import User
from app.services.working_paper_service import WorkingPaperService
from app.models.workpaper_models import WpIndex, WorkingPaper, WpFileStatus

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

    try:
        result = await svc.assign_workpaper(
            db=db, wp_id=wp_id, project_id=project_id,
            assigned_to=data.assigned_to,
            reviewer=data.reviewer,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── 重新分配通知（仅当 assigned_to 变更且原编制人存在时） ──
    if (
        data.assigned_to is not None
        and old_assigned_to is not None
        and old_assigned_to != data.assigned_to
    ):
        try:
            await _send_reassignment_notifications(
                db=db,
                project_id=project_id,
                wp_id=wp_id,
                old_assignee_id=old_assigned_to,
                new_assignee_id=data.assigned_to,
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
    """专用提交复核端点 — 统一校验 5 项门禁后流转复核状态

    门禁：1.复核人已分配 2.QC阻断=0 3.未解决批注=0 4.AI未确认=0 5.open复核意见已回复
    全部通过后：
      - 编制状态 → under_review
      - 复核状态 → pending_level1
    """
    wp_result = await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp = wp_result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # 只有 edit_complete 或 revision_required→edit_complete 后才能提交
    if wp.status != WpFileStatus.edit_complete:
        current_s = wp.status.value if wp.status else "unknown"
        raise HTTPException(
            status_code=400,
            detail=f"当前编制状态 {current_s} 不允许提交复核，需先完成编制（edit_complete）",
        )

    # ── Phase 14: 统一门禁引擎评估 ──
    try:
        from app.services.gate_engine import gate_engine as _gate_engine
        gate_result = await _gate_engine.evaluate(
            db=db,
            gate_type="submit_review",
            project_id=project_id,
            wp_id=wp_id,
            actor_id=current_user.id,
            context={"wp_status": wp.status, "year": getattr(wp, 'year', None)},
        )
        if gate_result.decision == "block":
            return {
                "status": "blocked",
                "blocking_reasons": [
                    f"[{h.rule_code}] {h.message}" for h in gate_result.hit_rules
                    if h.severity == "blocking"
                ],
                "hit_rules": [
                    {
                        "rule_code": h.rule_code,
                        "error_code": h.error_code,
                        "severity": h.severity,
                        "message": h.message,
                        "location": h.location,
                        "suggested_action": h.suggested_action,
                    }
                    for h in gate_result.hit_rules
                ],
                "can_submit": False,
                "trace_id": gate_result.trace_id,
            }
    except Exception as _gate_err:
        import logging
        logging.getLogger(__name__).warning(f"[GATE] submit_review gate eval failed: {_gate_err}")
        # 门禁引擎故障不阻断，降级走原有门禁逻辑

    # ── Phase 14: SoD 职责分离校验 ──
    try:
        from app.services.sod_guard_service import sod_guard_service as _sod_svc
        sod_result = await _sod_svc.check(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
            actor_id=current_user.id,
            target_role="reviewer",
        )
        if not sod_result.allowed:
            raise HTTPException(status_code=403, detail={
                "error_code": "SOD_CONFLICT_DETECTED",
                "message": sod_result.conflict_type,
                "policy_code": sod_result.policy_code,
                "trace_id": sod_result.trace_id,
            })
    except HTTPException:
        raise
    except Exception as _sod_err:
        import logging
        logging.getLogger(__name__).warning(f"[SOD] submit_review sod check failed: {_sod_err}")

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
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning("统计未解决复核意见失败 wp=%s: %s", wp_id, e)

    # 门禁 4：无未确认 AI 内容
    ai_pending_result = await db.execute(
        sa.select(sa.func.count()).select_from(AIContent).where(
            AIContent.project_id == project_id,
            AIContent.workpaper_id == wp_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == sa.false(),
        )
    )
    unconfirmed_ai_count = ai_pending_result.scalar() or 0
    if unconfirmed_ai_count > 0:
        blocking_reasons.append(f"{unconfirmed_ai_count} 项未确认的 AI 生成内容")

    # 门禁 5：所有 open 状态的复核意见必须已被 replied
    from app.models.workpaper_models import ReviewRecord, ReviewCommentStatus
    open_unreplied = await db.execute(
        sa.select(sa.func.count()).select_from(ReviewRecord).where(
            ReviewRecord.working_paper_id == wp_id,
            ReviewRecord.status == ReviewCommentStatus.open,
            ReviewRecord.is_deleted == sa.false(),
        )
    )
    unreplied_count = open_unreplied.scalar() or 0
    if unreplied_count > 0:
        blocking_reasons.append(f"{unreplied_count} 条复核意见未回复（状态仍为 open）")

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
            db=db, wp_id=wp_id, new_review_status="pending_level1", project_id=project_id,
        )
        await db.commit()

        # 自动同步程序状态（底稿提交复核→程序标记completed）
        try:
            from app.models.procedure_models import ProcedureInstance
            wp_result = await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == (
                    sa.select(WorkingPaper.wp_index_id).where(WorkingPaper.id == wp_id).scalar_subquery()
                ))
            )
            wp_code_row = wp_result.scalar_one_or_none()
            if wp_code_row:
                await db.execute(
                    sa.update(ProcedureInstance).where(
                        ProcedureInstance.project_id == project_id,
                        ProcedureInstance.wp_code == wp_code_row,
                        ProcedureInstance.is_deleted == sa.false(),
                    ).values(execution_status="completed")
                )
                await db.commit()
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("底稿提交后同步程序状态失败 wp=%s: %s", wp_id, e)  # 程序联动失败不阻断提交

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
    _lock_check=Depends(check_consol_lock),
):
    """更新底稿复核任务状态（需 review 权限）

    复核人操作：
      pending_level1 → level1_in_progress → level1_passed/level1_rejected
      pending_level2 → level2_in_progress → level2_passed/level2_rejected
    """
    svc = WorkingPaperService()
    try:
        result = await svc.update_review_status(
            db=db, wp_id=wp_id, new_review_status=data.review_status,
            project_id=project_id, reason=data.reason,
            rejected_by_id=current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
