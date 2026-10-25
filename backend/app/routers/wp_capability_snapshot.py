"""GET workpaper capability snapshot — formula-toolbar Task 3."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import get_current_user
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
    # Minimal projection until Task 3 wires full visibility grants.
    raw = (getattr(user, "role", None) or getattr(user, "user_role", None) or "assignee")
    value = str(raw).strip().lower()
    if value in {"admin", "supervisor", "lead", "assignee", "reviewer", "readonly"}:
        return value  # type: ignore[return-value]
    if value in {"superadmin", "system_admin"}:
        return "admin"
    return "assignee"


@router.get("/{wp_id}/capability-snapshot")
def get_capability_snapshot(
    wp_id: str,
    project_id: str = Query(..., min_length=1),
    owner_epoch: int = Query(0, ge=0, alias="ownerEpoch"),
    sheet_uid: str | None = Query(None, alias="sheetUid"),
    project_member: bool = Query(True, alias="projectMember"),
    wp_visible: bool = Query(True, alias="wpVisible"),
    role: RoleQuery | None = Query(None),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Issue a versioned capability snapshot for the workpaper shell.

    Query flags ``projectMember`` / ``wpVisible`` are temporary wiring knobs for
    fail-closed tests until this endpoint is fully bound to ``wp_visibility``.
    Production callers should omit them (defaults true) and rely on gate wiring.
    """
    principal = CapabilityPrincipal(
        role=role or _role_of(user),
        user_id=str(getattr(user, "id", "") or getattr(user, "user_id", "") or "unknown"),
        project_id=project_id,
        wp_id=wp_id,
        sheet_uid=sheet_uid,
        project_member=project_member,
        wp_visible=wp_visible,
    )
    return build_capability_snapshot(principal, owner_epoch=owner_epoch)


@router.post("/{wp_id}/capability-assert")
def assert_capability_action(
    wp_id: str,
    body: CapabilityActionBody,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Server-side revalidation for a shell action (provider/save/AI/review/rail)."""
    _ = user  # auth required; decision is snapshot-authoritative here
    if body.snapshot.get("wpId") not in (None, wp_id) and body.snapshot.get("wpId") != wp_id:
        raise HTTPException(status_code=400, detail="snapshot wpId mismatch")
    decision = assert_snapshot_action_allowed(
        body.snapshot,
        body.capability,
        owner_epoch=body.ownerEpoch,
    )
    return {"wpId": wp_id, "capability": body.capability, **decision.to_wire()}
