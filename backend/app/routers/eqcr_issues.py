"""EQCR 问题单 API — Phase 7 F2

提供 EQCR 问题单的创建、列表和回复功能。
可见性过滤：仅 EQCR 角色 + 项目团队（manager/signing_partner/auditor）可访问。
使用 IssueTicket 模型，source='eqcr'。
回复通过 IssueTicket parent_id 自引用实现线程。

Validates: Requirements F2.1, F2.2, F2.3, F2.4, F2.5, F2.6, F2.7, F2.8
"""

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase15_models import IssueTicket

router = APIRouter(
    prefix="/api/projects/{project_id}/eqcr-issues",
    tags=["eqcr-issues"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EqcrIssueCreate(BaseModel):
    severity: Literal["blocker", "major", "minor", "suggestion"]
    category: str
    title: str
    description: str | None = None
    wp_id: str | None = None


class EqcrIssueReply(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Helper: check EQCR visibility (EQCR + project team)
# ---------------------------------------------------------------------------


async def _check_eqcr_visibility(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> str:
    """验证用户有权访问 EQCR 问题单。返回项目角色。

    允许：admin / eqcr / manager / signing_partner / auditor
    """
    if user.role.value == "admin":
        return "admin"

    from app.models.staff_models import ProjectAssignment, StaffMember

    result = await db.execute(
        select(ProjectAssignment.role)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.project_id == project_id,
            StaffMember.user_id == user.id,
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
    )
    role = result.scalar_one_or_none()

    allowed_roles = {"eqcr", "manager", "signing_partner", "auditor"}
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="无权访问 EQCR 问题单")

    return role


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/eqcr-issues
# ---------------------------------------------------------------------------


@router.get("")
async def list_eqcr_issues(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """列出 EQCR 问题单（仅 EQCR + 项目团队可见）。

    排序：severity 降序 + created_at 升序。
    返回统计摘要：open/in_fix/closed 计数。
    """
    await _check_eqcr_visibility(project_id, current_user, db)

    # Severity ordering: blocker > major > minor > suggestion
    severity_order = sql_text(
        "CASE severity "
        "WHEN 'blocker' THEN 1 "
        "WHEN 'major' THEN 2 "
        "WHEN 'minor' THEN 3 "
        "WHEN 'suggestion' THEN 4 "
        "ELSE 5 END"
    )

    # Query issues with source='eqcr' and no parent (top-level only)
    result = await db.execute(
        select(IssueTicket)
        .where(
            IssueTicket.project_id == project_id,
            IssueTicket.source == "eqcr",
            IssueTicket.thread_id == None,  # noqa: E711 - top-level issues only
        )
        .order_by(severity_order, IssueTicket.created_at.asc())
    )
    issues = result.scalars().all()

    # Build summary
    summary = {"open": 0, "in_fix": 0, "closed": 0}
    for issue in issues:
        status = issue.status
        if status in summary:
            summary[status] += 1

    items = []
    for issue in issues:
        items.append({
            "id": str(issue.id),
            "project_id": str(issue.project_id),
            "severity": issue.severity,
            "category": issue.category,
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "owner_id": str(issue.owner_id),
            "wp_id": str(issue.wp_id) if issue.wp_id else None,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        })

    return {"items": items, "summary": summary}


# ---------------------------------------------------------------------------
# POST /api/projects/{project_id}/eqcr-issues
# ---------------------------------------------------------------------------


@router.post("")
async def create_eqcr_issue(
    project_id: uuid.UUID,
    body: EqcrIssueCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """创建 EQCR 问题单（自动设置 source='eqcr'）。"""
    await _check_eqcr_visibility(project_id, current_user, db)

    issue_id = uuid.uuid4()
    trace_id = str(uuid.uuid4())[:16]
    now = datetime.utcnow()

    issue = IssueTicket(
        id=issue_id,
        project_id=project_id,
        source="eqcr",
        severity=body.severity,
        category=body.category,
        title=body.title,
        description=body.description,
        owner_id=current_user.id,
        wp_id=uuid.UUID(body.wp_id) if body.wp_id else None,
        status="open",
        trace_id=trace_id,
        created_at=now,
        updated_at=now,
    )
    db.add(issue)
    await db.commit()

    return {
        "id": str(issue_id),
        "project_id": str(project_id),
        "source": "eqcr",
        "severity": body.severity,
        "category": body.category,
        "title": body.title,
        "description": body.description,
        "status": "open",
        "owner_id": str(current_user.id),
        "created_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /api/projects/{project_id}/eqcr-issues/{issue_id}/reply
# ---------------------------------------------------------------------------


@router.post("/{issue_id}/reply")
async def reply_eqcr_issue(
    project_id: uuid.UUID,
    issue_id: uuid.UUID,
    body: EqcrIssueReply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """回复 EQCR 问题单。

    使用 IssueTicket 自引用（thread_id 指向原问题单 ID）实现线程。
    回复触发 SSE 通知。
    """
    await _check_eqcr_visibility(project_id, current_user, db)

    # Verify parent issue exists
    result = await db.execute(
        select(IssueTicket).where(
            IssueTicket.id == issue_id,
            IssueTicket.project_id == project_id,
            IssueTicket.source == "eqcr",
        )
    )
    parent_issue = result.scalar_one_or_none()
    if parent_issue is None:
        raise HTTPException(status_code=404, detail="问题单不存在")

    # Create reply as a new IssueTicket with thread_id pointing to parent
    reply_id = uuid.uuid4()
    trace_id = str(uuid.uuid4())[:16]
    now = datetime.utcnow()

    reply = IssueTicket(
        id=reply_id,
        project_id=project_id,
        source="eqcr",
        severity=parent_issue.severity,
        category=parent_issue.category,
        title=f"Re: {parent_issue.title}",
        description=body.content,
        owner_id=current_user.id,
        thread_id=issue_id,  # self-reference to parent
        status="open",
        trace_id=trace_id,
        created_at=now,
        updated_at=now,
    )
    db.add(reply)

    # Trigger SSE notification (best-effort)
    try:
        from app.core.redis import redis_client
        if redis_client:
            sse_payload = json.dumps({
                "event_type": "eqcr_issue_reply",
                "data": {
                    "issue_id": str(issue_id),
                    "reply_id": str(reply_id),
                    "project_id": str(project_id),
                    "replier": str(current_user.id),
                    "timestamp": now.isoformat(),
                },
            })
            await redis_client.publish("sse:eqcr_notifications", sse_payload)
    except Exception:
        pass  # SSE failure should not block reply

    await db.commit()

    return {
        "id": str(reply_id),
        "issue_id": str(issue_id),
        "content": body.content,
        "owner_id": str(current_user.id),
        "created_at": now.isoformat(),
    }
