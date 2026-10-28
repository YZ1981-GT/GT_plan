"""增强批量委派端点

POST /api/workpapers/batch-assign-enhanced
  - 支持策略 manual / round_robin / by_level
  - 可选 override_assignments 批量微调
  - 提交后一次性发 Notification 给所有被分配的人

包装现有 POST /api/projects/{id}/working-papers/batch-assign 的逻辑。
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Notification, Project, User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.batch_assign_strategy import (
    AssignmentResult,
    CandidateInfo,
    Strategy,
    WorkpaperInfo,
    compute_assignments,
)
from app.services.notification_service import NotificationService
from app.services.notification_types import ASSIGNMENT_CREATED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers", tags=["batch-assign-enhanced"])


# ── 请求/响应 Schema ──────────────────────────────────────────────


class OverrideAssignment(BaseModel):
    wp_id: UUID
    user_id: UUID


class BatchAssignEnhancedRequest(BaseModel):
    wp_ids: list[UUID] = Field(..., min_length=1, description="待分配底稿 ID 列表")
    strategy: Literal["manual", "round_robin", "by_level"] = Field(
        ..., description="分配策略"
    )
    candidates: list[UUID] = Field(
        ..., min_length=1, description="候选人 user_id 列表"
    )
    reviewer_id: UUID | None = Field(None, description="复核人（可选，统一设置）")
    override_assignments: list[OverrideAssignment] | None = Field(
        None, description="手动微调覆盖（可选）"
    )
    # 被委派人可见范围不含目标循环（400 out_of_scope）时带理由重试 ⇒ 同事务扩大其可见范围
    # （spec procedure-trim-generation-delegation-chain 需求 4.4）
    expand_scope: bool = False
    scope_reason: str | None = Field(None, max_length=500)


class AssignmentItem(BaseModel):
    wp_id: UUID
    user_id: UUID
    wp_code: str | None = None
    wp_name: str | None = None


class BatchAssignEnhancedResponse(BaseModel):
    assignments: list[AssignmentItem]
    updated: int
    notifications_sent: int
    message: str


# ── 端点实现 ──────────────────────────────────────────────────────


@router.post("/batch-assign-enhanced", response_model=BatchAssignEnhancedResponse)
async def batch_assign_enhanced(
    data: BatchAssignEnhancedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """增强批量委派：支持策略分配 + override 微调 + 通知

    权限（Batch 1 P0.3）：
    - 所有 wp_ids 必须属于同一项目
    - 当前用户须是该项目的委派人（``ensure_project_delegator``：admin，或本项目唯一有效委派角色为
      合伙人 / 签字合伙人 / 经理；与 ``PUT /workpaper-leads`` 同一判定）

    spec procedure-trim-generation-delegation-chain 任务 12：编制人改走底稿主编委派事务（已裁 / 在回收站
    拒绝、被委派人须看得到该循环、委派历史与可见性策略版本、投影同步）；复核人仍直写但须是本项目成员；
    任一失败整批回滚，通知 / 事件 / 审计只在成功后发。
    """

    # 1. 查询底稿信息（含 WpIndex 的 audit_cycle）
    wp_query = (
        sa.select(
            WorkingPaper.id,
            WorkingPaper.project_id,
            WpIndex.wp_code,
            WpIndex.wp_name,
            WpIndex.audit_cycle,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id.in_(data.wp_ids),
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    rows = (await db.execute(wp_query)).all()

    if not rows:
        raise HTTPException(status_code=404, detail="未找到有效底稿")

    # Batch 1 P0.3: 校验所有 wp 同属一个项目
    project_ids_seen = {row.project_id for row in rows}
    if len(project_ids_seen) > 1:
        raise HTTPException(
            status_code=400,
            detail="批量委派的底稿必须属于同一项目",
        )
    target_project_id = project_ids_seen.pop()

    # Batch 1 P0.3: 权限守卫 — 当前用户是该项目的委派人（与底稿主编委派同一判定；原手写查询在同一用户
    # 有两份人员记录时 scalar_one_or_none 抛 500）
    from app.services.procedure_authorization import ensure_project_delegator

    try:
        await ensure_project_delegator(db, current_user, target_project_id)
    except HTTPException as exc:
        raise HTTPException(
            status_code=403,
            detail="权限不足：只有项目经理或合伙人可以批量委派",
        ) from exc

    # 构建 WorkpaperInfo 列表
    workpapers: list[WorkpaperInfo] = []
    wp_meta: dict[UUID, dict] = {}  # wp_id → {wp_code, wp_name, project_id}
    for row in rows:
        wp_id = row.id
        workpapers.append(
            WorkpaperInfo(
                wp_id=wp_id,
                audit_cycle=row.audit_cycle,
                complexity=None,  # WpIndex 当前无 complexity 字段，走 audit_cycle 映射
            )
        )
        wp_meta[wp_id] = {
            "wp_code": row.wp_code,
            "wp_name": row.wp_name,
            "project_id": row.project_id,
        }

    # 2. 如果是 by_level 策略，需要查询候选人角色信息
    if data.strategy == "by_level":
        from app.models.staff_models import ProjectAssignment, StaffMember

        # 获取底稿所属项目（取第一个底稿的项目，批量委派通常在同一项目内）
        project_ids = list(set(m["project_id"] for m in wp_meta.values()))

        # 查询候选人在项目中的角色
        role_query = (
            sa.select(StaffMember.user_id, ProjectAssignment.role)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                StaffMember.user_id.in_(data.candidates),
                ProjectAssignment.project_id.in_(project_ids),
                ProjectAssignment.is_deleted == sa.false(),
            )
        )
        role_rows = (await db.execute(role_query)).all()
        role_map: dict[UUID, str] = {row.user_id: row.role for row in role_rows}

        candidates_info = [
            CandidateInfo(
                user_id=uid,
                role=role_map.get(uid, "auditor"),  # 默认当 auditor
            )
            for uid in data.candidates
        ]
        candidates_arg: list[UUID] | list[CandidateInfo] = candidates_info
    else:
        candidates_arg = data.candidates

    # 3. 计算分配结果
    override_results = None
    if data.override_assignments:
        override_results = [
            AssignmentResult(wp_id=o.wp_id, user_id=o.user_id)
            for o in data.override_assignments
        ]

    assignments = compute_assignments(
        strategy=data.strategy,
        workpapers=workpapers,
        candidates=candidates_arg,
        override_assignments=override_results,
    )

    # 4. 执行分配：编制人走底稿主编委派事务；复核人直写但须是本项目成员（任一失败整批回滚）
    from app.services.wp_visibility.delegation_guard import DelegationError
    from app.services.wp_visibility.lead_delegation_entry import (
        delegate_workpaper_leads,
        resolve_project_member_user,
    )

    try:
        outcome = await delegate_workpaper_leads(
            db, target_project_id, [(a.wp_id, a.user_id) for a in assignments],
            actor_user_id=current_user.id, expand_scope=data.expand_scope, scope_reason=data.scope_reason,
        )
        if data.reviewer_id is not None:
            reviewer_user = await resolve_project_member_user(db, target_project_id, data.reviewer_id)
            if reviewer_user is None:
                raise HTTPException(status_code=400, detail={
                    "error": "reviewer_not_member", "message": "复核人不是本项目成员，请先在团队分配中加入"})
            for wp in (await db.execute(sa.select(WorkingPaper).where(
                WorkingPaper.id.in_(outcome.updated)))).scalars().all():
                wp.reviewer = reviewer_user
    except DelegationError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.http_status, detail=exc.http_detail()) from exc
    except Exception:
        await db.rollback()
        raise
    updated = len(outcome.updated)
    done = set(outcome.updated)
    # 只对真正委派成功的底稿发通知 / 事件 / 回执；被委派人一律用解析出的用户 id（候选可能传人员 id）
    assignments = [
        AssignmentResult(wp_id=a.wp_id, user_id=outcome.assignee_users.get(a.wp_id, a.user_id))
        for a in assignments if a.wp_id in done
    ]

    await db.flush()

    # 5. 发送通知给所有被分配的人（去重）
    notif_service = NotificationService(db)
    notified_users: set[UUID] = set()
    notifications_sent = 0

    # 获取项目名称（用于通知内容）
    project_names: dict[UUID, str] = {}
    for pid in set(m["project_id"] for m in wp_meta.values()):
        proj = (await db.execute(
            sa.select(Project.name).where(Project.id == pid)
        )).scalar_one_or_none()
        project_names[pid] = proj or "未知项目"

    # 按被分配人聚合通知
    user_wp_map: dict[UUID, list[dict]] = {}
    for assignment in assignments:
        uid = assignment.user_id
        meta = wp_meta.get(assignment.wp_id, {})
        if uid not in user_wp_map:
            user_wp_map[uid] = []
        user_wp_map[uid].append(meta)

    for user_id, wp_list in user_wp_map.items():
        # 取第一个底稿的项目名作为通知标题
        first_meta = wp_list[0]
        project_name = project_names.get(first_meta.get("project_id"), "未知项目")
        wp_count = len(wp_list)

        if wp_count == 1:
            content = f"项目「{project_name}」的底稿 {first_meta.get('wp_code', '')} 已委派给您，请及时处理"
        else:
            content = f"项目「{project_name}」的 {wp_count} 张底稿已委派给您，请及时处理"

        result = await notif_service.send_notification(
            user_id=user_id,
            notification_type=ASSIGNMENT_CREATED,
            title=f"新委派通知 — {wp_count} 张底稿",
            content=content,
            metadata={
                "object_type": "project",
                "object_id": str(first_meta.get("project_id", "")),
            },
        )
        if result:
            notifications_sent += 1

    await db.commit()

    # Batch 3 Fix 3: 发 WP_ASSIGNED 事件供 event_handlers 级联
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus
        for assignment in assignments:
            meta = wp_meta.get(assignment.wp_id, {})
            await event_bus.publish(EventPayload(
                event_type=EventType.WORKPAPER_ASSIGNED,
                project_id=meta.get("project_id", target_project_id),
                extra={
                    "wp_id": str(assignment.wp_id),
                    "assigned_to": str(assignment.user_id),
                },
            ))
    except Exception:
        logger.warning("[BAE] event publish failed, non-blocking")

    # Batch 2 P2: 审计日志记录批量委派操作
    try:
        from app.services.audit_logger_enhanced import audit_logger
        await audit_logger.log_action(
            user_id=current_user.id,
            action="batch_assign",
            object_type="project",
            object_id=target_project_id,
            project_id=target_project_id,
            details={
                "strategy": data.strategy,
                "wp_count": updated,
                "candidates": [str(uid) for uid in data.candidates],
                "reviewer_id": str(data.reviewer_id) if data.reviewer_id else None,
                "assignments": [
                    {"wp_id": str(a.wp_id), "user_id": str(a.user_id)}
                    for a in assignments
                ],
            },
        )
    except Exception as _audit_err:
        logger.warning("batch_assign audit log failed: %s", _audit_err)

    # 6. 构建响应
    response_items = []
    for assignment in assignments:
        meta = wp_meta.get(assignment.wp_id, {})
        response_items.append(
            AssignmentItem(
                wp_id=assignment.wp_id,
                user_id=assignment.user_id,
                wp_code=meta.get("wp_code"),
                wp_name=meta.get("wp_name"),
            )
        )

    return BatchAssignEnhancedResponse(
        assignments=response_items,
        updated=updated,
        notifications_sent=notifications_sent,
        message=f"已分配 {updated} 张底稿，{notifications_sent} 人收到通知",
    )
