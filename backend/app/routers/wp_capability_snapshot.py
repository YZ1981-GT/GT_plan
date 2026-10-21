"""GET workpaper capability snapshot — formula-toolbar Task 3."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import authorize_wp_read, get_current_user
from app.models.core import User
from app.services.workpaper_capability import (
    CapabilityPrincipal,
    RoleName,
    assert_snapshot_action_allowed,
    build_capability_snapshot,
)

router = APIRouter(prefix="/api/workpapers", tags=["workpaper-capability"])

RoleQuery = Literal[
    "admin",
    "supervisor",
    "lead",
    "assignee",
    "reviewer",
    "readonly",
    "anonymous",
]


class CapabilityActionBody(BaseModel):
    capability: Literal[
        "formulaView",
        "formulaEditUser",
        "formulaHistory",
        "aiReviewPage",
        "aiReviewBatch",
        "aiAssistChat",
        "humanReviewRead",
        "humanReviewWrite",
        "guidanceRead",
    ]
    ownerEpoch: int = Field(..., ge=0)
    snapshot: dict[str, Any]


def _role_of(user: User) -> RoleName:
    raw = getattr(user, "role", None) or getattr(user, "user_role", None)
    value = raw.value if hasattr(raw, "value") else str(raw or "")
    mapping: dict[str, RoleName] = {
        "admin": "admin",
        "partner": "supervisor",
        "manager": "lead",
        "auditor": "assignee",
        "qc": "reviewer",
        "eqcr": "reviewer",
        "readonly": "readonly",
    }
    return mapping.get(value.strip().lower(), "anonymous")


@router.get("/{wp_id}/capability-snapshot")
async def get_capability_snapshot(
    wp_id: UUID,
    project_id: UUID = Query(...),
    owner_epoch: int = Query(0, ge=0, alias="ownerEpoch"),
    sheet_uid: str | None = Query(None, alias="sheetUid"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按认证用户与数据库归属签发能力快照；不信任客户端角色/成员/可见性标志。"""
    actual_project_id = await authorize_wp_read(db, user, wp_id)
    if actual_project_id != project_id:
        raise HTTPException(status_code=403, detail="project_id 与底稿归属不一致")
    principal = CapabilityPrincipal(
        role=_role_of(user),
        user_id=str(user.id),
        project_id=str(actual_project_id),
        wp_id=str(wp_id),
        sheet_uid=sheet_uid,
        project_member=True,
        wp_visible=True,
    )
    return build_capability_snapshot(principal, owner_epoch=owner_epoch)


@router.post("/{wp_id}/capability-assert")
async def assert_capability_action(
    wp_id: UUID,
    body: CapabilityActionBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按当前认证用户和数据库归属重新计算能力，不信任客户端 snapshot 决策。"""
    actual_project_id = await authorize_wp_read(db, user, wp_id)
    snapshot_project = str(body.snapshot.get("projectId") or "")
    if snapshot_project and snapshot_project != str(actual_project_id):
        raise HTTPException(status_code=403, detail="snapshot projectId mismatch")
    snapshot_wp = str(body.snapshot.get("wpId") or "")
    if snapshot_wp and snapshot_wp != str(wp_id):
        raise HTTPException(status_code=400, detail="snapshot wpId mismatch")
    principal = CapabilityPrincipal(
        role=_role_of(user),
        user_id=str(user.id),
        project_id=str(actual_project_id),
        wp_id=str(wp_id),
        sheet_uid=body.snapshot.get("sheetUid"),
        project_member=True,
        wp_visible=True,
    )
    authoritative = build_capability_snapshot(
        principal,
        owner_epoch=body.ownerEpoch,
    )
    decision = assert_snapshot_action_allowed(
        authoritative,
        body.capability,
        owner_epoch=body.ownerEpoch,
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.zh_message or "权限不足")
    return {"wpId": str(wp_id), "capability": body.capability, **decision.to_wire()}
