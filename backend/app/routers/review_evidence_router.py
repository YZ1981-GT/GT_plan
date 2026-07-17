"""Review Evidence Router — 复核证据绑定/关闭/重开 API（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R9, R10, R12
Design: §4.6 Review 快照, §5.4 stale/Review/统一图, §6.2 主要端点 (Review row)
Properties: P21 (Blocking Review 关闭门禁), P22 (复核自动重开)
UAT: UAT-11（关闭 Blocking Review 后替换依据 → 自动重开；QC/EQCR 页面显示版本/hash/确认/
     path/locator；re_review_required 阻断 QC/EQCR/partner 完成）

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/reviews）：
  - POST ``/{review_id}/evidence`` — 绑定证据到复核意见（冻结 raised 快照）
  - POST ``/{review_id}/close``    — 关闭复核（review.close；权限+说明+非 stale ref 门禁）
  - POST ``/{review_id}/reopen``   — 依据失效自动重开（→ re_review_required）
  - GET  ``/{review_id}``          — 复核状态 + 证据展示（版本/hash/确认/stale/locator）
  - GET  ``/completion-block``     — QC/EQCR/partner 完成是否被 re_review_required 阻断

thin router：关闭门禁委托 ``ReviewEvidenceService.evaluate_close_gate``（P21 五条件），
快照 shape 用 ``create_snapshot``。持久化落 ``review_evidence_snapshots`` / ``review_closes``
两张既有表（design §4.6）。

GAP 说明（如实报告，见文件尾）：``ReviewEvidenceService`` 是纯内存逻辑服务，无复核意见
（severity/status/content）持久化——意见本体存于 review_conversations 子系统。本 router
从 ``review_closes`` + ``review_evidence_snapshots`` 派生关闭/重开/re_review_required 状态，
意见属性（severity）由请求体传入；证据 staleness 由 evidence_refs.status 实时判定。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.routers.evidence_governance_common import (
    get_user_role,
    isoformat_or_none,
    parse_uuid,
)
from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.review_evidence_service import (
    ReviewEvidenceService,
    ReviewOpinion,
    ReviewStatus,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/reviews",
    tags=["evidence-governance", "review"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────


class BindEvidenceRequest(BaseModel):
    evidence_ref_id: str = Field(..., min_length=1)
    target_version: str | None = None
    target_hash: str | None = None
    locator: dict | None = None


class CloseReviewRequest(BaseModel):
    closing_explanation: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(default="high", pattern=r"^(low|medium|high|critical)$")


class ReopenReviewRequest(BaseModel):
    reason: str = Field(default="evidence_invalidated", max_length=200)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — load current bound evidence + staleness from persisted snapshots
# ─────────────────────────────────────────────────────────────────────────────


async def _load_current_evidence_refs(
    db: AsyncSession, review_id: uuid.UUID, phase: str = "raised"
) -> list[dict[str, Any]]:
    """Load bound evidence snapshots joined to evidence_refs for staleness (P21/P22).

    A ref is considered stale when its evidence_refs.status != 'active' (replaced /
    deactivated). Returns dicts in the shape ReviewEvidenceService expects.
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT s.evidence_ref_id, s.target_version, s.target_hash, "
                "s.locator, s.is_stale, r.status AS ref_status, r.evidence_type "
                "FROM review_evidence_snapshots s "
                "LEFT JOIN evidence_refs r ON r.id = s.evidence_ref_id "
                "WHERE s.review_id = :rid AND s.snapshot_phase = :phase"
            ),
            {"rid": str(review_id), "phase": phase},
        )
    ).mappings().all()

    refs: list[dict[str, Any]] = []
    for r in rows:
        ref_status = r["ref_status"]
        stale = bool(r["is_stale"]) or (ref_status is not None and ref_status != "active")
        refs.append(
            {
                "evidence_ref_id": str(r["evidence_ref_id"]),
                "evidence_type": r["evidence_type"] or "",
                "target_version": r["target_version"],
                "target_hash": r["target_hash"] or "",
                "locator": r["locator"] or {},
                "stale": stale,
            }
        )
    return refs


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{review_id}/evidence", status_code=201)
async def bind_evidence(
    project_id: str,
    year: int,
    review_id: str,
    body: BindEvidenceRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """绑定证据到复核意见并冻结 raised 快照（R10.1）。"""
    pid = parse_uuid(project_id, "project_id")
    rid = parse_uuid(review_id, "review_id")
    ref_id = parse_uuid(body.evidence_ref_id, "evidence_ref_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # 边界先于业务：evidence_ref 必须存在于本 scope（否则脱敏 404，避免 FK 500）
    ref_row = (
        await db.execute(
            sa.text(
                "SELECT id FROM evidence_refs WHERE id = :rid AND project_id = :pid LIMIT 1"
            ),
            {"rid": str(ref_id), "pid": str(pid)},
        )
    ).first()
    if ref_row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, "evidence ref not found"
        )

    idem_key = idempotency_key or f"review:bind:{review_id}:{body.evidence_ref_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = ReviewEvidenceService()
        # 用服务构造快照 shape（保证与 close 逻辑一致），再持久化到 review_evidence_snapshots
        snap = svc.create_snapshot(
            evidence_ref_id=str(ref_id),
            evidence_type="",
            target_version=0,
            target_hash=body.target_hash or "",
            locator=json.dumps(body.locator) if body.locator else "",
        )
        snap_id = uuid.uuid4()
        await txn.db.execute(
            sa.text(
                "INSERT INTO review_evidence_snapshots "
                "(id, review_id, project_id, audit_year, evidence_ref_id, "
                " target_version, target_hash, locator, snapshot_phase, is_stale, "
                " actor_type, actor_user_id, actor_service_identity_id) "
                "VALUES (:id, :rid, :pid, :yr, :eref, :tv, :th, "
                " CAST(:loc AS JSONB), 'raised', false, "
                " :at, :auid, :asid)"
            ),
            {
                "id": str(snap_id),
                "rid": str(rid),
                "pid": str(pid),
                "yr": txn.audit_year or year,
                "eref": str(ref_id),
                "tv": body.target_version,
                "th": body.target_hash,
                "loc": json.dumps(body.locator) if body.locator else None,
                "at": txn.actor.actor_type.value,
                "auid": (
                    str(txn.actor.actor_user_id) if txn.actor.actor_user_id else None
                ),
                "asid": (
                    str(txn.actor.actor_service_identity_id)
                    if txn.actor.actor_service_identity_id
                    else None
                ),
            },
        )
        await txn.db.flush()
        return {"snapshot_id": str(snap_id), "snapshot_ref": snap.snapshot_id}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="review.bind_evidence",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "review_id": str(rid),
        "snapshot_id": cmd_result.result["snapshot_id"],
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/{review_id}/close")
async def close_review(
    project_id: str,
    year: int,
    review_id: str,
    body: CloseReviewRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """关闭复核（R10.2 / P21：权限 + 充分说明 + 至少一个非 stale ref；capability review.close）。

    门禁未通过 → EVIDENCE_GATE_BLOCKED（保留完整历史，目标零变化）。
    """
    pid = parse_uuid(project_id, "project_id")
    rid = parse_uuid(review_id, "review_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot close reviews",
        )

    idem_key = idempotency_key or f"review:close:{review_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        current_refs = await _load_current_evidence_refs(txn.db, rid, phase="raised")

        svc = ReviewEvidenceService()
        opinion = ReviewOpinion(
            opinion_id=str(rid),
            project_id=str(pid),
            audit_year=txn.audit_year or year,
            severity=body.severity,
            status=ReviewStatus.open.value,
            created_by_user_id=str(current_user.id),
        )
        # facade 已强制 capability review.close，故此处 has_close_permission=True
        gate = svc.evaluate_close_gate(
            opinion,
            closing_explanation=body.closing_explanation,
            closer_user_id=str(current_user.id),
            actor=txn.actor,
            has_close_permission=True,
            current_evidence_refs=current_refs,
        )
        if not gate.allowed:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.EVIDENCE_GATE_BLOCKED,
                "review close blocked: " + ",".join(r.value for r in gate.reject_reasons),
            )

        # 关闭成功 → 落 review_closes + closed 快照
        close_id = uuid.uuid4()
        await txn.db.execute(
            sa.text(
                "INSERT INTO review_closes "
                "(id, review_id, project_id, audit_year, close_note, "
                " closed_by_user_id, command_root_id, reopened) "
                "VALUES (:id, :rid, :pid, :yr, :note, :uid, :cmd, false)"
            ),
            {
                "id": str(close_id),
                "rid": str(rid),
                "pid": str(pid),
                "yr": txn.audit_year or year,
                "note": body.closing_explanation,
                "uid": str(current_user.id),
                "cmd": str(txn.command_root_id),
            },
        )
        # 冻结 closed-phase 快照（复制 raised 快照的证据引用）
        for ref in current_refs:
            await txn.db.execute(
                sa.text(
                    "INSERT INTO review_evidence_snapshots "
                    "(id, review_id, project_id, audit_year, evidence_ref_id, "
                    " target_version, target_hash, locator, snapshot_phase, is_stale, "
                    " actor_type, actor_user_id, actor_service_identity_id) "
                    "VALUES (:id, :rid, :pid, :yr, :eref, :tv, :th, "
                    " CAST(:loc AS JSONB), 'closed', :stale, "
                    " :at, :auid, :asid)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "rid": str(rid),
                    "pid": str(pid),
                    "yr": txn.audit_year or year,
                    "eref": ref["evidence_ref_id"],
                    "tv": ref.get("target_version"),
                    "th": ref.get("target_hash") or None,
                    "loc": json.dumps(ref.get("locator")) if ref.get("locator") else None,
                    "stale": bool(ref.get("stale")),
                    "at": txn.actor.actor_type.value,
                    "auid": (
                        str(txn.actor.actor_user_id) if txn.actor.actor_user_id else None
                    ),
                    "asid": (
                        str(txn.actor.actor_service_identity_id)
                        if txn.actor.actor_service_identity_id
                        else None
                    ),
                },
            )
        await txn.db.flush()
        return {"close_id": str(close_id)}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="review.close",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="review.close",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "review_id": str(rid),
        "status": "closed",
        "close_id": cmd_result.result["close_id"],
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/{review_id}/reopen")
async def reopen_review(
    project_id: str,
    year: int,
    review_id: str,
    body: ReopenReviewRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """依据失效后自动重开复核 → re_review_required（R10.3 / P22）。

    幂等：已重开则再次调用无副作用。无已关闭记录 → INVALID_STATE_TRANSITION。
    """
    pid = parse_uuid(project_id, "project_id")
    rid = parse_uuid(review_id, "review_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"review:reopen:{review_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        # 找最近的未重开关闭记录
        row = (
            await txn.db.execute(
                sa.text(
                    "SELECT id, reopened FROM review_closes "
                    "WHERE review_id = :rid AND project_id = :pid "
                    "ORDER BY closed_at DESC LIMIT 1"
                ),
                {"rid": str(rid), "pid": str(pid)},
            )
        ).mappings().first()
        if row is None:
            raise EvidenceGovernanceError(
                EvidenceErrorCode.INVALID_STATE_TRANSITION,
                "review has no closed record to reopen",
            )
        if row["reopened"]:
            return {"reopened": True, "already": True}

        await txn.db.execute(
            sa.text(
                "UPDATE review_closes SET reopened = true, reopened_at = now() "
                "WHERE id = :id"
            ),
            {"id": str(row["id"])},
        )
        await txn.db.flush()
        return {"reopened": True, "already": False}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="review.reopen",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "review_id": str(rid),
        "status": ReviewStatus.re_review_required.value,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/completion-block")
async def completion_block(
    project_id: str,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """QC/EQCR/partner 完成是否被 re_review_required 阻断（R10.3；只读）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    rows = (
        await db.execute(
            sa.text(
                "SELECT review_id FROM review_closes "
                "WHERE project_id = :pid AND reopened = true "
                "AND (audit_year = :yr OR audit_year IS NULL)"
            ),
            {"pid": str(pid), "yr": year},
        )
    ).mappings().all()

    blocking = [str(r["review_id"]) for r in rows]
    return {
        "blocked": len(blocking) > 0,
        "re_review_required_reviews": blocking,
    }


@router.get("/{review_id}")
async def get_review_state(
    project_id: str,
    year: int,
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """复核状态 + 证据展示（版本/hash/OCR-AI 确认/stale/locator；R10.4）。"""
    pid = parse_uuid(project_id, "project_id")
    rid = parse_uuid(review_id, "review_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    close_row = (
        await db.execute(
            sa.text(
                "SELECT id, close_note, closed_by_user_id, reopened, closed_at, reopened_at "
                "FROM review_closes WHERE review_id = :rid AND project_id = :pid "
                "ORDER BY closed_at DESC LIMIT 1"
            ),
            {"rid": str(rid), "pid": str(pid)},
        )
    ).mappings().first()

    if close_row is None:
        status = ReviewStatus.open.value
    elif close_row["reopened"]:
        status = ReviewStatus.re_review_required.value
    else:
        status = ReviewStatus.closed.value

    # 证据展示：优先 closed 快照，否则 raised
    phase = "closed" if close_row is not None else "raised"
    refs = await _load_current_evidence_refs(db, rid, phase=phase)
    if not refs and phase == "closed":
        refs = await _load_current_evidence_refs(db, rid, phase="raised")

    return {
        "review_id": str(rid),
        "status": status,
        "close_note": close_row["close_note"] if close_row else None,
        "closed_by_user_id": (
            str(close_row["closed_by_user_id"]) if close_row else None
        ),
        "closed_at": isoformat_or_none(close_row["closed_at"]) if close_row else None,
        "reopened_at": (
            isoformat_or_none(close_row["reopened_at"]) if close_row else None
        ),
        "evidence": [
            {
                "evidence_ref_id": r["evidence_ref_id"],
                "evidence_type": r["evidence_type"],
                "target_version": r["target_version"],
                "content_hash": r["target_hash"],
                "is_stale": r["stale"],
                "locator": r["locator"],
            }
            for r in refs
        ],
    }
