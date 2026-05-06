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
    - 当前用户对该项目必须有 edit 权限（project_assignment.role IN manager/signing_partner
      或 role='admin'）
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

    # Batch 1 P0.3: 权限守卫 — 当前用户对该项目有 edit 权限
    if current_user.role.value != "admin":
        from app.models.staff_models import ProjectAssignment as _PA, StaffMember as _SM

        staff_id_stmt = sa.select(_SM.id).where(
            _SM.user_id == current_user.id,
            _SM.is_deleted == sa.false(),
        )
        staff_id = (await db.execute(staff_id_stmt)).scalar_one_or_none()

        allowed = False
        if staff_id:
            pa_stmt = sa.select(_PA.id).where(
                _PA.staff_id == staff_id,
                _PA.project_id == target_project_id,
                _PA.role.in_(["manager", "signing_partner"]),
                _PA.is_deleted == sa.false(),
            )
            if (await db.execute(pa_stmt)).scalar_one_or_none():
                allowed = True
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="权限不足：只有项目经理或签字合伙人可以批量委派",
            )

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

    # 4. 执行分配（更新数据库）
    updated = 0
    for assignment in assignments:
        result = await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == assignment.wp_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        wp = result.scalar_one_or_none()
        if not wp:
            continue
        wp.assigned_to = assignment.user_id
        if data.reviewer_id is not None:
            wp.reviewer = data.reviewer_id
        updated += 1

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
