"""Legal Hold / Retention Router — 法定保全与保留期清理 API（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2, R12, R13
Design: §5.5 Archive/Retention/Legal Hold, §6.2 主要端点 (Archive/Hold row)
Properties: P26 (Legal Hold 单调保护零效果), P27 (Purge 四条件)
UAT: UAT-13（veto：active hold 内 delete/purge/overwrite 对所有角色含 admin/紧急授权
     恒零效果；purge 仅在 hold 已解除 ∧ retention 届满 ∧ 授权 ∧ 无悬空 active ref 时进行）

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/legal-holds）：
  - POST ``/``                       — 创建法定保全（legal_hold.create）
  - GET  ``/``                       — 列出本 scope 的保全（只读）
  - GET  ``/{hold_id}/scope``        — 列出保全固化的 direct/transitive 范围（只读）
  - POST ``/{hold_id}/release``      — 解除保全（legal_hold.release，released_by 人工 FK）
  - POST ``/purge-jobs``             — 清理任务：强制四条件门禁（retention.purge）

thin router：仅委托 ``RetentionLegalHoldService``（activate_hold / release_hold /
evaluate_purge / purge），不重写任何图闭包或门禁逻辑。写命令经
``EvidenceGovernanceFacade`` 保证 scope + capability + 短事务 + command-root + outbox。

脱敏：scope/权限/不存在统一 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``；active hold 内破坏性操作
返回 ``LEGAL_HOLD_ACTIVE``（HTTP 423，delta=0）。破坏性 delete/overwrite 的零效果由各
拥有引擎在其删除/替换路径调用 ``RetentionLegalHoldService.authorize_destructive`` 强制；
本 router 暴露的破坏性面是 purge-jobs（受 P27 四条件门禁）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, Query
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
from app.services.evidence_governance.retention_legal_hold_service import (
    RetentionLegalHoldService,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard
from app.services.evidence_governance.unified_graph_builder import GraphScope

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/legal-holds",
    tags=["evidence-governance", "legal-hold"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────


class SeedNode(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=50)
    node_id: str = Field(..., min_length=1, max_length=200)


class CreateHoldRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    seed_nodes: list[SeedNode] = Field(default_factory=list)


class ReleaseHoldRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class PurgeJobRequest(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=50)
    node_id: str = Field(..., min_length=1, max_length=200)
    retention_expired: bool = Field(
        default=False,
        description="保留期是否已届满（由 retention policy 判定；四条件之一）",
    )
    purge_reason: str = Field(default="retention_expired", max_length=50)
    content_hash: str | None = None
    retention_policy_version: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_legal_hold(
    project_id: str,
    year: int,
    body: CreateHoldRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """创建法定保全并固化统一图闭包（R13.1，capability legal_hold.create）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"legal_hold:create:{pid}:{year}:{body.reason[:40]}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = RetentionLegalHoldService(txn.db)
        scope = GraphScope(project_id=txn.project_id, audit_year=txn.audit_year or year)
        seeds = [(s.node_type, s.node_id) for s in body.seed_nodes]
        result = await svc.activate_hold(
            scope=scope,
            reason=body.reason,
            actor=txn.actor,
            seed_nodes=seeds,
        )
        return result

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="legal_hold.create",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="legal_hold.create",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result
    return {
        "legal_hold_id": str(result.legal_hold_id),
        "graph_watermark": result.graph_watermark,
        "direct_count": result.direct_count,
        "transitive_count": result.transitive_count,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("")
async def list_legal_holds(
    project_id: str,
    year: int,
    state: str | None = Query(None, description="active|released"),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """列出本 scope 的法定保全（只读）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    clauses = ["project_id = :pid", "(audit_year = :yr OR audit_year IS NULL)"]
    params: dict[str, Any] = {"pid": str(pid), "yr": year, "lim": limit}
    if state in ("active", "released"):
        clauses.append("state = :state")
        params["state"] = state

    rows = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, audit_year, reason, state, graph_watermark, "
                "release_reason, released_by_user_id, released_at, created_at "
                "FROM legal_holds WHERE " + " AND ".join(clauses) + " "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": str(r["id"]),
                "project_id": str(r["project_id"]),
                "audit_year": r["audit_year"],
                "reason": r["reason"],
                "state": r["state"],
                "graph_watermark": r["graph_watermark"],
                "release_reason": r["release_reason"],
                "released_by_user_id": (
                    str(r["released_by_user_id"]) if r["released_by_user_id"] else None
                ),
                "released_at": isoformat_or_none(r["released_at"]),
                "created_at": isoformat_or_none(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.get("/{hold_id}/scope")
async def get_hold_scope(
    project_id: str,
    year: int,
    hold_id: str,
    scope_kind: str | None = Query(None, description="direct|transitive"),
    limit: int = Query(200, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """列出保全固化的 direct/transitive 保护范围（只读，P26）。"""
    pid = parse_uuid(project_id, "project_id")
    hid = parse_uuid(hold_id, "hold_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # 验证 hold 属于本 scope（不存在/越权同一脱敏码）
    hold_row = (
        await db.execute(
            sa.text(
                "SELECT id FROM legal_holds WHERE id = :hid AND project_id = :pid LIMIT 1"
            ),
            {"hid": str(hid), "pid": str(pid)},
        )
    ).first()
    if hold_row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, "hold not found"
        )

    clauses = ["legal_hold_id = :hid", "is_active = true"]
    params: dict[str, Any] = {"hid": str(hid), "lim": limit}
    if scope_kind in ("direct", "transitive"):
        clauses.append("scope_kind = :sk")
        params["sk"] = scope_kind

    rows = (
        await db.execute(
            sa.text(
                "SELECT id, node_type, node_id, scope_kind, is_active, created_at "
                "FROM legal_hold_scopes WHERE " + " AND ".join(clauses) + " "
                "ORDER BY scope_kind, node_type, node_id LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    return {
        "hold_id": str(hid),
        "nodes": [
            {
                "node_type": r["node_type"],
                "node_id": r["node_id"],
                "scope_kind": r["scope_kind"],
                "is_active": r["is_active"],
            }
            for r in rows
        ],
    }


@router.post("/{hold_id}/release")
async def release_legal_hold(
    project_id: str,
    year: int,
    hold_id: str,
    body: ReleaseHoldRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """解除法定保全（R13.3，capability legal_hold.release，released_by 独立人工 FK）。"""
    pid = parse_uuid(project_id, "project_id")
    hid = parse_uuid(hold_id, "hold_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Service Identity 不得解除（design §2.2，服务侧也会再拦）
    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot release hold",
        )

    idem_key = idempotency_key or f"legal_hold:release:{hold_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = RetentionLegalHoldService(txn.db)
        await svc.release_hold(
            legal_hold_id=hid,
            released_by_user_id=current_user.id
            if isinstance(current_user.id, uuid.UUID)
            else uuid.UUID(str(current_user.id)),
            release_reason=body.reason,
            actor=txn.actor,
        )
        return {"released": True}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="legal_hold.release",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="legal_hold.release",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "hold_id": str(hid),
        "released": True,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/purge-jobs")
async def create_purge_job(
    project_id: str,
    year: int,
    body: PurgeJobRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """清理任务：强制 P27 四条件门禁（capability retention.purge）。

    仅当 hold 已解除 ∧ retention 届满 ∧ 主体具 retention.purge ∧ 无悬空 active ref 时
    授权清理并写入不可变墓碑；否则 delta=0（零效果）并返回未满足条件清单。UAT-13。
    """
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = (
        idempotency_key or f"retention:purge:{body.node_type}:{body.node_id}"
    )

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = RetentionLegalHoldService(txn.db)
        result = await svc.purge(
            project_id=txn.project_id,
            audit_year=txn.audit_year,
            node_type=body.node_type,
            node_id=body.node_id,
            actor_role=role,
            actor=txn.actor,
            retention_expired=body.retention_expired,
            purged_by_user_id=current_user.id
            if isinstance(current_user.id, uuid.UUID)
            else uuid.UUID(str(current_user.id)),
            purge_reason=body.purge_reason,
            content_hash=body.content_hash,
            retention_policy_version=body.retention_policy_version,
        )
        return result

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="retention.purge",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="retention.purge",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result
    return {
        "allowed": result.decision.allowed,
        "delta": result.decision.delta,
        "unmet_conditions": list(result.decision.unmet),
        "tombstone_id": str(result.tombstone_id) if result.tombstone_id else None,
        "command_root_id": str(cmd_result.command_root_id),
    }
