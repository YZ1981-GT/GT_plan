"""AI Evidence Gate / FormalOutput Router — AI 证据门禁 API（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R9, R10, R11
Design: §5.3 RAG/AI 与 FormalOutputGate, §6.2 主要端点 (RAG/AI + FormalOutput rows)
Properties: P17 (AI 状态门禁), P18 (AI 入口覆盖), P19 (确认内容变更失效)
UAT: UAT-10（底稿/附注/报告/复核 AI 入口均登记；未人工确认的 AI 草稿被 FormalOutput
     拒绝 → EVIDENCE_GATE_BLOCKED）

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/ai）：
  - POST ``/generations``                       — 登记 AI 生成（ai.generate）
  - GET  ``/generations/{content_id}``          — 查询 AI 内容状态（只读）
  - POST ``/generations/{content_id}/confirm``  — 人工确认（ai.confirm）
  - POST ``/generations/{content_id}/revise``   — 人工修订（ai.confirm）
  - POST ``/generations/{content_id}/reject``   — 人工拒绝（ai.confirm）
  - GET  ``/generations/{content_id}/eligibility`` — FormalOutput 资格检查（只读）
  - POST ``/formal-output/preflight``           — FormalOutput 前置门禁
  - POST ``/formal-output/finalize``            — FormalOutput 终态门禁（watermark 比对）

thin router：委托 ``AIEvidenceGate``（register_generation / confirm / revise / reject /
check_formal_output_eligibility）与 ``FormalOutputGate``（preflight / finalize），不重写
任何门禁规则。写命令经 ``EvidenceGovernanceFacade``。Service Identity 不得确认。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

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
from app.services.evidence_governance.ai_evidence_gate import (
    AIEvidenceGate,
    AiServiceStatus,
)
from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.formal_output_gate import FormalOutputGate
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/ai",
    tags=["evidence-governance", "ai-gate"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────


class RegisterGenerationRequest(BaseModel):
    entry_point: str = Field(..., min_length=1, max_length=100)
    prompt_hash: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=200)
    output: str = Field(...)
    context_refs: list[str] | None = None
    citation_snapshot_ids: list[str] | None = None
    service_status: str = Field(default="available", pattern=r"^(available|degraded|unavailable)$")
    wp_id: str | None = None
    target_cell: str | None = None


class ReviseContentRequest(BaseModel):
    new_output: str = Field(..., min_length=1)


class RejectContentRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class FormalOutputRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=200)
    target_type: str = Field(..., min_length=1, max_length=100)
    policy_version: str | None = None


class FormalOutputFinalizeRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=200)
    target_type: str = Field(..., min_length=1, max_length=100)
    preflight_watermark: str = Field(..., min_length=1)
    policy_version: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _uuid_list(values: list[str] | None) -> list[uuid.UUID] | None:
    if not values:
        return None
    out: list[uuid.UUID] = []
    for v in values:
        try:
            out.append(uuid.UUID(str(v)))
        except (ValueError, AttributeError, TypeError):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, "invalid ref id"
            )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# AI generation lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/generations", status_code=201)
async def register_generation(
    project_id: str,
    year: int,
    body: RegisterGenerationRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """登记 AI 生成（R8.1，capability ai.generate）。默认落 draft 生命周期状态。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"ai:generate:{body.entry_point}:{body.prompt_hash}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        gate = AIEvidenceGate(txn.db)
        return await gate.register_generation(
            entry_point=body.entry_point,
            prompt_hash=body.prompt_hash,
            model_name=body.model_name,
            output=body.output,
            actor=txn.actor,
            project_id=txn.project_id,
            audit_year=txn.audit_year or year,
            context_refs=_uuid_list(body.context_refs),
            citation_snapshot_ids=_uuid_list(body.citation_snapshot_ids),
            service_status=AiServiceStatus(body.service_status),
            wp_id=uuid.UUID(body.wp_id) if body.wp_id else None,
            target_cell=body.target_cell,
        )

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ai.generate",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ai.generate",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    reg = cmd_result.result
    return {
        "content_id": str(reg.content_id),
        "entry_point": reg.entry_point,
        "output_hash": reg.output_hash,
        "lifecycle_status": reg.lifecycle_status.value,
        "service_status": reg.service_status.value,
        "content_version": reg.content_version,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/generations/{content_id}")
async def get_generation(
    project_id: str,
    year: int,
    content_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """查询 AI 内容治理记录（只读）。"""
    import sqlalchemy as sa

    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(content_id, "content_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    row = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, audit_year, entry_point, model_name, "
                "service_status, output_hash, lifecycle_status, content_version, "
                "created_at FROM ai_content_governance "
                "WHERE id = :cid AND project_id = :pid LIMIT 1"
            ),
            {"cid": str(cid), "pid": str(pid)},
        )
    ).mappings().first()
    if row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, "content not found"
        )

    return {
        "content_id": str(row["id"]),
        "entry_point": row["entry_point"],
        "model_name": row["model_name"],
        "service_status": row["service_status"],
        "output_hash": row["output_hash"],
        "lifecycle_status": row["lifecycle_status"],
        "content_version": row["content_version"],
        "created_at": isoformat_or_none(row["created_at"]),
    }


@router.post("/generations/{content_id}/confirm")
async def confirm_generation(
    project_id: str,
    year: int,
    content_id: str,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """人工确认 AI 内容 draft→confirmed（capability ai.confirm；Service Identity 禁止）。"""
    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(content_id, "content_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot confirm AI content",
        )

    idem_key = idempotency_key or f"ai:confirm:{content_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        gate = AIEvidenceGate(txn.db)
        confirmed = await gate.confirm_content(
            content_id=cid, actor=txn.actor, project_id=txn.project_id
        )
        return {"confirmed": confirmed}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ai.confirm",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ai.confirm",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "content_id": str(cid),
        "confirmed": cmd_result.result["confirmed"],
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/generations/{content_id}/revise")
async def revise_generation(
    project_id: str,
    year: int,
    content_id: str,
    body: ReviseContentRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """人工修订 AI 内容（创建新版本，原记录标 revised；capability ai.confirm）。"""
    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(content_id, "content_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot revise AI content",
        )

    idem_key = idempotency_key or f"ai:revise:{content_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        gate = AIEvidenceGate(txn.db)
        return await gate.revise_content(
            content_id=cid,
            new_output=body.new_output,
            actor=txn.actor,
            project_id=txn.project_id,
        )

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ai.revise",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ai.confirm",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    reg = cmd_result.result
    return {
        "content_id": str(reg.content_id),
        "lifecycle_status": reg.lifecycle_status.value,
        "content_version": reg.content_version,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/generations/{content_id}/reject")
async def reject_generation(
    project_id: str,
    year: int,
    content_id: str,
    body: RejectContentRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """人工拒绝 AI 内容 draft→rejected（capability ai.confirm）。"""
    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(content_id, "content_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot reject AI content",
        )

    idem_key = idempotency_key or f"ai:reject:{content_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        gate = AIEvidenceGate(txn.db)
        rejected = await gate.reject_content(
            content_id=cid,
            reason=body.reason,
            actor=txn.actor,
            project_id=txn.project_id,
        )
        return {"rejected": rejected}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ai.reject",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ai.confirm",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    return {
        "content_id": str(cid),
        "rejected": cmd_result.result["rejected"],
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/generations/{content_id}/eligibility")
async def check_eligibility(
    project_id: str,
    year: int,
    content_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """检查 AI 内容能否进入 FormalOutput（R8.3 / P17；只读）。

    未人工确认 / hash 变更 / 依据 stale / 生成时服务不可用 → 返回 blocked 及原因。UAT-10。
    """
    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(content_id, "content_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    gate = AIEvidenceGate(db)
    result = await gate.check_formal_output_eligibility(
        content_id=cid, actor=actor, project_id=pid
    )

    return {
        "content_id": str(result.content_id),
        "status": result.status.value,
        "eligible": result.eligible,
        "reasons": [
            {"code": r.code, "description": r.description, "detail": r.detail}
            for r in result.reasons
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# FormalOutput preflight / finalize gate
# ─────────────────────────────────────────────────────────────────────────────


def _gate_evaluation_to_dict(ev: Any) -> dict:
    return {
        "phase": ev.phase.value,
        "verdict": ev.verdict.value,
        "passed": ev.passed,
        "target_id": ev.target_id,
        "target_type": ev.target_type,
        "policy_version": ev.policy_version,
        "watermark": ev.watermark,
        "evidence_count": ev.evidence_count,
        "degraded": ev.degraded,
        "blocking_reasons": [
            {
                "code": r.code.value,
                "evidence_id": r.evidence_id,
                "description": r.description,
                "detail": r.detail,
            }
            for r in ev.blocking_reasons
        ],
    }


@router.post("/formal-output/preflight")
async def formal_output_preflight(
    project_id: str,
    year: int,
    body: FormalOutputRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """FormalOutput 前置门禁（R8/R11；返回 watermark 供 finalize 比对）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    gate = FormalOutputGate()
    ev = await gate.preflight(
        body.target_id, body.target_type, policy_version=body.policy_version
    )
    return _gate_evaluation_to_dict(ev)


@router.post("/formal-output/finalize")
async def formal_output_finalize(
    project_id: str,
    year: int,
    body: FormalOutputFinalizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """FormalOutput 终态门禁（重跑校验 + watermark 比对；变更即失败重试）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    gate = FormalOutputGate()
    ev = await gate.finalize(
        body.target_id,
        body.target_type,
        body.preflight_watermark,
        policy_version=body.policy_version,
    )
    return _gate_evaluation_to_dict(ev)
