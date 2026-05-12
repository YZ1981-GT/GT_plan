"""底稿催办端点 — Round 2 需求 4

POST /api/projects/{project_id}/workpapers/{wp_id}/remind
  body: {message?: str}
  resp: {ticket_id, notification_id, remind_count, allowed_next}

7 天内最多 3 次催办（按自然日计），超过返回 429。
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.workpaper_remind_service import workpaper_remind_service

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["workpaper-remind"],
)


# ── 请求/响应 Schema ──────────────────────────────────────────────


class RemindRequest(BaseModel):
    message: Optional[str] = Field(None, description="自定义催办消息（可选）")


class RemindResponse(BaseModel):
    ticket_id: str
    notification_id: Optional[str] = None
    remind_count: int
    allowed_next: Optional[str] = None


# ── 端点 ──────────────────────────────────────────────────────────


@router.post("/{wp_id}/remind", response_model=RemindResponse)
async def remind_workpaper(
    project_id: UUID,
    wp_id: UUID,
    body: RemindRequest = RemindRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """催办底稿编制人。

    创建 IssueTicket(source='reminder') + Notification(type='workpaper_reminder')。
    7 天内同一底稿最多催办 3 次，超限返回 429。
    """
    result = await workpaper_remind_service.remind(
        db=db,
        project_id=project_id,
        wp_id=wp_id,
        operator_id=current_user.id,
        message=body.message,
    )
    return RemindResponse(**result)


# ── 催办升级到合伙人 ──────────────────────────────────────────────


class EscalateRequest(BaseModel):
    wp_ids: list[UUID] = Field(..., min_length=1, description="需要升级的底稿 ID 列表")
    reason: str = Field("催办 3 次未响应", description="升级原因")


class EscalateResponse(BaseModel):
    escalated_count: int
    notification_ids: list[str]


@router.post("/escalate-to-partner", response_model=EscalateResponse)
async def escalate_to_partner(
    project_id: UUID,
    body: EscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """将逾期底稿升级通知合伙人。

    PM 催办 3 次后仍未响应时使用。
    创建 Notification(type='workpaper_escalation') 发送给项目签字合伙人。
    """
    from app.models.staff_models import ProjectAssignment, StaffMember
    from app.services.notification_service import NotificationService
    import sqlalchemy as sa

    # 查找项目签字合伙人
    partner_stmt = (
        sa.select(StaffMember.user_id)
        .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.role.in_(["partner", "signing_partner"]),
            ProjectAssignment.is_deleted == sa.false(),
            StaffMember.user_id.isnot(None),
        )
    )
    partner_user_ids = [r[0] for r in (await db.execute(partner_stmt)).all()]

    if not partner_user_ids:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="项目未配置签字合伙人")

    notification_ids = []
    notif_svc = NotificationService(db)
    for partner_uid in partner_user_ids:
        notif = await notif_svc.create_notification(
            user_id=partner_uid,
            notification_type="workpaper_escalation",
            title=f"底稿逾期升级：{len(body.wp_ids)} 个底稿催办 3 次未响应",
            content=f"项目经理已催办 3 次仍未完成，原因：{body.reason}。请关注并协调处理。",
            jump_route=f"/projects/{project_id}/progress-board",
            metadata={"project_id": str(project_id), "wp_ids": [str(w) for w in body.wp_ids]},
        )
        notification_ids.append(str(notif.id))

    await db.commit()
    return EscalateResponse(
        escalated_count=len(body.wp_ids),
        notification_ids=notification_ids,
    )
