"""Evidence Ref Router — 证据关系 API（Task 4.4, Wave 3）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2, R3, R4
Design: §6.2 主要端点 (EvidenceRef row)

端点：
  - GET  /references — 双向查询（R4.3: 从源端与目标端查询相同 EvidenceRef）
  - GET  /references/{ref_id} — 单个引用详情
  - GET  /impact — 直接 + 传递影响查询（R4.4）
  - POST /references — 创建引用（委托 EvidenceRefService, R3.1）
  - POST /references/{ref_id}/deactivate — 停用引用（R3.4）

所有端点：
  - cursor 分页（默认 limit<=100，硬上限 200）（Design §6.1）
  - scope 校验（path project_id/year 与对象权威 scope 一致）
  - 脱敏错误（SCOPE_NOT_FOUND_OR_FORBIDDEN 不含目标信息）（R4.2）
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.evidence_governance.evidence_ref_query_service import (
    EvidenceRefQueryService,
)
from app.services.evidence_governance.evidence_ref_service import (
    CreateEvidenceRefRequest,
    EvidenceRefService,
)
from app.services.evidence_governance.facade import (
    CommandRequest,
    CommandTxn,
    EvidenceGovernanceFacade,
)
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ERROR_CODE_HTTP_STATUS,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.metadata_gate import MetadataCompletenessGate
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/refs",
    tags=["evidence-governance"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────


class CreateRefRequest(BaseModel):
    """创建 EvidenceRef 请求体。"""

    source_type: str = Field(..., min_length=1, max_length=100)
    source_id: str = Field(..., min_length=1, max_length=200)
    source_version: int | None = None
    evidence_type: str = Field(..., min_length=1, max_length=100)
    evidence_id: str = Field(..., min_length=1, max_length=200)
    attachment_version_id: str | None = None
    target_version: int | None = None
    target_hash: str | None = None
    label: str | None = None
    context: str | None = None


class DeactivateRefRequest(BaseModel):
    """停用 EvidenceRef 请求体。"""

    reason: str = Field(..., min_length=1, max_length=500)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_project_id(project_id: str) -> uuid.UUID:
    """解析 path 中的 project_id，无效则抛脱敏错误。"""
    try:
        return uuid.UUID(project_id)
    except (ValueError, AttributeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )


def _build_ref_response(ref: Any) -> dict:
    """将 EvidenceRefRow / dataclass 转换为 JSON 响应字典。"""
    return {
        "id": str(ref.id),
        "project_id": str(ref.project_id),
        "audit_year": ref.audit_year,
        "source_type": ref.source_type,
        "source_id": ref.source_id,
        "source_version": ref.source_version,
        "evidence_type": ref.evidence_type,
        "evidence_id": ref.evidence_id,
        "attachment_version_id": str(ref.attachment_version_id)
        if ref.attachment_version_id
        else None,
        "target_version": ref.target_version,
        "target_hash": ref.target_hash,
        "label": ref.label,
        "context": ref.context,
        "intent_hash": ref.intent_hash,
        "status": ref.status,
        "created_at": (
            ref.created_at.isoformat() if hasattr(ref.created_at, "isoformat") else str(ref.created_at)
        ),
    }


def _error_response(exc: EvidenceGovernanceError) -> dict:
    """构造脱敏错误字典（design §7.2）。"""
    return {
        "error_code": exc.error_code.value,
        "message": _desensitize_message(exc.error_code),
        "retryable": exc.retryable,
    }


def _desensitize_message(code: EvidenceErrorCode) -> str:
    """返回脱敏的通用提示（R4.2: 不泄露目标信息）。"""
    messages = {
        EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN: "目标不可访问",
        EvidenceErrorCode.VERSION_CONFLICT: "版本冲突",
        EvidenceErrorCode.METADATA_INCOMPLETE: "元数据不完整",
        EvidenceErrorCode.EVIDENCE_GATE_BLOCKED: "证据门禁阻断",
    }
    return messages.get(code, "操作失败")


async def _get_user_role(db: AsyncSession, user: Any, project_id: uuid.UUID) -> str:
    """获取用户在项目中的角色。"""
    import sqlalchemy as sa

    # 先检查系统角色
    if hasattr(user, "role"):
        role = user.role
        if role in ("admin", "partner"):
            return role

    # 查项目分配角色
    row = (
        await db.execute(
            sa.text(
                "SELECT role FROM project_users "
                "WHERE project_id = :pid AND user_id = :uid "
                "AND is_deleted = false LIMIT 1"
            ),
            {"pid": str(project_id), "uid": str(user.id)},
        )
    ).mappings().first()
    if row:
        return row["role"]

    # 回退系统角色
    if hasattr(user, "role"):
        return user.role
    return "readonly"


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/references")
async def list_evidence_refs(
    project_id: str,
    year: int,
    direction: str = Query("source", description="source|evidence（双向查询）"),
    source_type: str | None = Query(None),
    source_id: str | None = Query(None),
    evidence_type: str | None = Query(None),
    evidence_id: str | None = Query(None),
    status: str | None = Query(None, description="active|inactive"),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """双向查询 EvidenceRef（R4.3: 从源端与目标端查询相同引用）。

    cursor 分页，默认 limit<=100，硬上限 200（design §6.1）。
    """
    pid = _parse_project_id(project_id)
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    # scope 校验
    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    query_svc = EvidenceRefQueryService(db)

    if direction == "evidence" and evidence_id:
        page = await query_svc.query_refs_to_evidence(
            project_id=pid,
            audit_year=year,
            evidence_type=evidence_type or "",
            evidence_id=evidence_id,
            actor=actor,
            status=status or "active",
            cursor=cursor,
            limit=limit,
        )
    else:
        page = await query_svc.query_refs_from_source(
            project_id=pid,
            audit_year=year,
            source_type=source_type or "",
            source_id=source_id or "",
            actor=actor,
            status=status or "active",
            cursor=cursor,
            limit=limit,
        )

    return {
        "items": [_build_ref_response(r) for r in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


@router.get("/references/{ref_id}")
async def get_evidence_ref(
    project_id: str,
    year: int,
    ref_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """获取单个 EvidenceRef 详情。"""
    pid = _parse_project_id(project_id)
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    try:
        rid = uuid.UUID(ref_id)
    except (ValueError, AttributeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )

    query_svc = EvidenceRefQueryService(db)
    # 使用 find_active_ref_by_intent 不适用此处；直接查单个
    import sqlalchemy as sa

    row = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, audit_year, source_type, source_id, "
                "source_version, evidence_type, evidence_id, attachment_version_id, "
                "target_version, target_hash, label, context, intent_hash, status, "
                "created_at "
                "FROM evidence_refs WHERE id = :rid AND project_id = :pid LIMIT 1"
            ),
            {"rid": str(rid), "pid": str(pid)},
        )
    ).mappings().first()

    if row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )

    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "audit_year": row["audit_year"],
        "source_type": row["source_type"],
        "source_id": row["source_id"],
        "source_version": row["source_version"],
        "evidence_type": row["evidence_type"],
        "evidence_id": row["evidence_id"],
        "attachment_version_id": str(row["attachment_version_id"])
        if row["attachment_version_id"]
        else None,
        "target_version": row["target_version"],
        "target_hash": row["target_hash"],
        "label": row["label"],
        "context": row["context"],
        "intent_hash": row["intent_hash"],
        "status": row["status"],
        "created_at": (
            row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"])
        ),
    }


@router.get("/impact")
async def query_impact(
    project_id: str,
    year: int,
    source_type: str = Query(...),
    source_id: str = Query(...),
    max_depth: int = Query(50, ge=1, le=50),
    limit: int = Query(200, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """查询证据影响范围 — 直接 + 传递引用（R4.4）。

    返回去重后的直接与传递引用，只包含当前项目、年度及用户有权读取的对象。
    """
    pid = _parse_project_id(project_id)
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    query_svc = EvidenceRefQueryService(db)
    # NOTE: service signature is query_impact(*, target_type, target_id, project_id,
    # audit_year, actor, max_depth). The impact traversal walks edges where the given
    # node is the *source* (source changes → targets become stale), so the requested
    # source_type/source_id map to the service's target_type/target_id parameters.
    result = await query_svc.query_impact(
        target_type=source_type,
        target_id=source_id,
        project_id=pid,
        audit_year=year,
        actor=actor,
        max_depth=max_depth,
    )

    return {
        "nodes": [
            {
                "target_type": n.target_type,
                "target_id": n.target_id,
                "distance": n.distance,
                "path": n.path,
            }
            for n in result.nodes
        ],
        "total_visited": result.total_visited,
        "truncated": result.truncated,
    }


@router.post("/references", status_code=201)
async def create_evidence_ref(
    project_id: str,
    year: int,
    body: CreateRefRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """创建 EvidenceRef（R3.1: 持久保存引用）。

    委托 EvidenceRefService.create_ref()，包含：
    - 元数据完整门禁（R2.1）
    - 同 scope/权限/版本/hash 校验
    - 活动 intent 幂等（R3.3）
    """
    pid = _parse_project_id(project_id)
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    # 边界先于业务：source_id / evidence_id 必须是合法 UUID（全部 10 个 typed adapter
    # 都以 UUID 主键解析证据目标；见 typed_adapters.py）。非 UUID 无法标识任何真实对象，
    # 且直接绑定到 UUID 列会触发 asyncpg DataError → 事务中止 → HTTP 500。按 design §7.2，
    # 否决必须是脱敏的干净 4xx，绝不能是 500。因此在任何 DB 读之前就以
    # SCOPE_NOT_FOUND_OR_FORBIDDEN 拒绝畸形 id（与安全读取端点 _parse_uuid 同一边界模式）。
    for _field_val in (body.source_id, body.evidence_id):
        try:
            uuid.UUID(str(_field_val))
        except (ValueError, AttributeError, TypeError):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "scope not found or forbidden",
            )

    # 元数据完整门禁（R2.1: 不完整时禁止新建正式 EvidenceRef）
    if body.attachment_version_id:
        # 查找关联附件 ID
        import sqlalchemy as sa

        att_row = (
            await db.execute(
                sa.text(
                    "SELECT attachment_id FROM attachment_versions "
                    "WHERE id = :avid LIMIT 1"
                ),
                {"avid": body.attachment_version_id},
            )
        ).mappings().first()
        if att_row:
            gate = MetadataCompletenessGate(db)
            await gate.assert_complete_for_ref(uuid.UUID(str(att_row["attachment_id"])))

    idem_key = idempotency_key or f"ref:{body.source_type}:{body.source_id}:{body.evidence_type}:{body.evidence_id}"

    # EvidenceRefService.create_ref() itself runs the command through the facade
    # (scope + capability + short transaction + command-root + outbox). The router
    # therefore delegates directly and does NOT double-wrap in a second facade command.
    # CreateEvidenceRefRequest has NO `actor` field — actor is a keyword-only arg on
    # create_ref (create_ref(*, request, actor, actor_role, idempotency_key=None, ...)).
    req = CreateEvidenceRefRequest(
        project_id=pid,
        audit_year=year,
        source_type=body.source_type,
        source_id=body.source_id,
        source_version=body.source_version,
        evidence_type=body.evidence_type,
        evidence_id=body.evidence_id,
        attachment_version_id=(
            uuid.UUID(body.attachment_version_id)
            if body.attachment_version_id
            else None
        ),
        target_version=body.target_version,
        target_hash=body.target_hash,
        label=body.label,
        context=body.context,
    )

    svc = EvidenceRefService(db)
    cmd_result = await svc.create_ref(
        request=req,
        actor=actor,
        actor_role=role,
        idempotency_key=idem_key,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result  # EvidenceRefResult(ref_id, intent_hash, idempotent_hit, dependency_id)
    return {
        "id": str(result.ref_id),
        "intent_hash": result.intent_hash,
        "idempotent_hit": result.idempotent_hit,
        "dependency_id": str(result.dependency_id) if result.dependency_id else None,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.post("/references/{ref_id}/deactivate")
async def deactivate_evidence_ref(
    project_id: str,
    year: int,
    ref_id: str,
    body: DeactivateRefRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """停用 EvidenceRef（R3.4: 要求原因、保留历史、停止参与新 FormalOutput）。

    注意：停用不受元数据门禁限制（仅创建受限）。
    """
    pid = _parse_project_id(project_id)
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    try:
        rid = uuid.UUID(ref_id)
    except (ValueError, AttributeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )

    idem_key = idempotency_key or f"deactivate:{ref_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        query_svc = EvidenceRefQueryService(txn.db)
        result = await query_svc.deactivate_ref(
            ref_id=rid,
            project_id=txn.project_id,
            audit_year=txn.audit_year or year,
            reason=body.reason,
            actor=txn.actor,
        )
        # 停用后经统一 outbox（facade 事务）触发下游 stale 传播 / 影响评估。
        # 由 facade 填充 project_id/event_id/actor_type/command_root_id（NOT NULL 列），
        # 保持单一权威 outbox 机制（服务层不再直接写 evidence_outbox）。
        await txn.enqueue_outbox(
            event_type="evidence_ref.deactivated",
            payload={
                "ref_id": str(rid),
                "previous_status": result.previous_status,
                "new_status": result.new_status,
                "reason": result.reason,
            },
        )
        return result

    try:
        cmd_result = await facade.execute(
            CommandRequest(
                command_type="evidence_ref.deactivate",
                idempotency_key=idem_key,
                actor=actor,
                actor_role=role,
                project_id=pid,
                audit_year=year,
                capability="evidence_ref.deactivate",
                object_type="evidence_ref",
                object_id=rid,
            ),
            _business,
        )
    except EvidenceGovernanceError:
        raise

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result
    return {
        "ref_id": str(result.ref_id),
        "previous_status": result.previous_status,
        "new_status": result.new_status,
        "reason": result.reason,
        "command_root_id": str(cmd_result.command_root_id),
    }
