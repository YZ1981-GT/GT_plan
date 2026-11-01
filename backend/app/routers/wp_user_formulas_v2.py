"""User formula v2 HTTP surface — additive to legacy dict API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models.core import User
from app.services.user_formula_v2 import (
    COMMAND_VERSION,
    DEFAULT_V2_STORE,
    InMemoryAuditGate,
    apply_batch_mutate,
    history_for,
)
from app.services.workpaper_capability import (
    CapabilityPrincipal,
    assert_snapshot_action_allowed,
    build_capability_snapshot,
)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/user-formulas/v2",
    tags=["workpaper-user-formulas-v2"],
)

_AUDIT = InMemoryAuditGate()


class BatchMutateBody(BaseModel):
    operationId: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    capabilitySnapshot: dict[str, Any] | None = None
    ownerEpoch: int = 0


@router.get("")
def list_user_formulas_v2(
    wp_id: str,
    location_digest_q: str | None = Query(None, alias="locationDigest"),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = user
    rows = DEFAULT_V2_STORE.list_for_location(None)
    if location_digest_q:
        rows = [r for r in rows if r.location_digest == location_digest_q]
    return {
        "wpId": wp_id,
        "contractVersion": COMMAND_VERSION,
        "formulas": [
            {
                "formulaId": r.formula_id,
                "version": r.version,
                "expression": r.expression,
                "formulaFunction": r.formula_function,
                "ruleCategory": r.rule_category,
                "refs": r.refs,
                "target": r.target,
                "locationDigest": r.location_digest,
            }
            for r in rows
            if not r.deleted
        ],
    }


@router.post(":batchMutate")
def batch_mutate_user_formulas_v2(
    wp_id: str,
    body: BatchMutateBody,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = wp_id
    operation_id = body.operationId or str(uuid4())
    allowed = True
    if body.capabilitySnapshot is not None:
        decision = assert_snapshot_action_allowed(
            body.capabilitySnapshot,
            "formulaEditUser",
            owner_epoch=body.ownerEpoch,
        )
        allowed = decision.allowed
    else:
        # Fail-closed default when no snapshot: build anonymous-denied unless admin-like.
        role = str(getattr(user, "role", "") or "assignee").lower()
        principal = CapabilityPrincipal(
            role="admin" if role in {"admin", "superadmin"} else "assignee",  # type: ignore[arg-type]
            user_id=str(getattr(user, "id", "u")),
            project_id="unknown",
            wp_id=wp_id,
        )
        snap = build_capability_snapshot(principal, owner_epoch=body.ownerEpoch)
        allowed = bool(snap["formulaEditUser"]["allowed"])

    return apply_batch_mutate(
        store=DEFAULT_V2_STORE,
        operation_id=operation_id,
        items=body.items,
        audit=_AUDIT,
        allowed=allowed,
    )


@router.get("/{formula_id}/history")
def user_formula_v2_history(
    wp_id: str,
    formula_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = (wp_id, user)
    hist = history_for(DEFAULT_V2_STORE, formula_id)
    if not hist["versions"] and DEFAULT_V2_STORE.get(formula_id) is None:
        raise HTTPException(status_code=404, detail="formula not found")
    return hist
