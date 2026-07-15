"""OCR Governance Router — OCR 治理 API（Task 5.5, Wave 4）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R5, R6, R12, R14
Design: §6.2 主要端点 (OCR row)

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/ocr）：
  - POST /jobs             — 提交 OCR 任务（ocr.start）
  - GET  /jobs/{job_id}    — 查询任务详情
  - POST /jobs/{job_id}/retry         — 重试失败任务（ocr.retry）
  - GET  /jobs/{job_id}/timeline      — 查询状态迁移时间线
  - GET  /jobs/{job_id}/results/{result_id}  — 获取 OCR 结果详情
  - PUT  /jobs/{job_id}/results/{result_id}/confirmations — 添加字段确认
  - GET  /jobs/{job_id}/results/{result_id}/confirmations — 列出所有确认
  - POST /jobs/{job_id}/results/{result_id}/writeback     — 执行写回
  - GET  /jobs/{job_id}/results/{result_id}/mapping       — 预览映射

所有端点：
  - scope 校验（path project_id/year == 对象权威 scope）
  - capability 校验（7 角色 + service actor）
  - 脱敏错误（SCOPE_NOT_FOUND_OR_FORBIDDEN）
  - 写回端点需 Idempotency-Key
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
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
from app.services.evidence_governance.ocr_confirmation_service import (
    OCRConfirmationService,
)
from app.services.evidence_governance.ocr_governance import (
    OCRGovernanceOrchestrator,
)
from app.services.evidence_governance.ocr_retry_service import OCRRetryService
from app.services.evidence_governance.ocr_writeback_service import OCRWritebackService
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/ocr",
    tags=["ocr-governance"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────


class SubmitOcrJobRequest(BaseModel):
    """提交 OCR 任务请求体。"""
    attachment_id: str = Field(..., min_length=1)
    attachment_version_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=64, max_length=64)
    parse_config: dict | None = None
    parse_config_version: str | None = None
    max_attempts: int = Field(default=5, ge=1, le=20)


class AddConfirmationRequest(BaseModel):
    """添加字段确认请求体。"""
    field_name: str = Field(..., min_length=1, max_length=200)
    decision: str = Field(..., pattern=r"^(accepted|corrected|rejected)$")
    confirmed_value: str | None = None
    reason: str | None = None


class ExecuteWritebackRequest(BaseModel):
    """执行写回请求体。"""
    target_type: str = Field(..., min_length=1, max_length=100)
    target_id: str = Field(..., min_length=1, max_length=200)
    target_version: int | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    """解析 UUID，无效则抛脱敏错误。"""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            f"invalid {field_name}",
        )


async def _get_user_role(db: AsyncSession, user: Any, project_id: uuid.UUID) -> str:
    """获取用户在项目中的角色。"""
    import sqlalchemy as sa

    if hasattr(user, "role"):
        role = user.role
        if role in ("admin", "partner"):
            return role

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

    if hasattr(user, "role"):
        return user.role
    return "readonly"


def _desensitize_message(code: EvidenceErrorCode) -> str:
    """返回脱敏的通用提示。"""
    messages = {
        EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN: "目标不可访问",
        EvidenceErrorCode.VERSION_CONFLICT: "版本冲突",
        EvidenceErrorCode.INVALID_STATE_TRANSITION: "状态迁移无效",
        EvidenceErrorCode.METADATA_INCOMPLETE: "元数据不完整",
    }
    return messages.get(code, "操作失败")


def _job_to_dict(job: Any) -> dict:
    """Convert OcrJob ORM object to response dict."""
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "audit_year": job.audit_year,
        "attachment_id": str(job.attachment_id),
        "attachment_version_id": str(job.attachment_version_id),
        "content_hash": job.content_hash,
        "parse_config": job.parse_config,
        "parse_config_version": job.parse_config_version,
        "state": job.state,
        "progress": job.progress,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "idempotency_key": job.idempotency_key,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": _isoformat(job.created_at),
        "updated_at": _isoformat(job.updated_at),
    }


def _isoformat(dt: Any) -> str | None:
    """Safe isoformat for nullable datetime."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/jobs", status_code=201)
async def submit_ocr_job(
    project_id: str,
    year: int,
    body: SubmitOcrJobRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """提交 OCR 任务（R5.1: 创建持久 OCR_Job）。

    需要 ocr.start 能力。幂等复用同一 attachment_version+hash+config 的活动任务。
    """
    pid = _parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"ocr:submit:{body.attachment_version_id}:{body.content_hash}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        orchestrator = OCRGovernanceOrchestrator(txn.db)
        job, created = await orchestrator.submit_ocr_job(
            project_id=txn.project_id,
            audit_year=txn.audit_year or year,
            attachment_id=uuid.UUID(body.attachment_id),
            attachment_version_id=uuid.UUID(body.attachment_version_id),
            content_hash=body.content_hash,
            parse_config=body.parse_config,
            parse_config_version=body.parse_config_version,
            actor=txn.actor,
            command_root_id=txn.command_root_id,
            max_attempts=body.max_attempts,
        )
        return {"job": job, "created": created}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ocr.submit",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ocr.start",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result
    return {
        "job": _job_to_dict(result["job"]),
        "created": result["created"],
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/jobs/{job_id}")
async def get_ocr_job(
    project_id: str,
    year: int,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """获取 OCR 任务详情 + 当前状态。

    所有项目成员可访问（无特殊 capability 要求）。
    """
    import sqlalchemy as sa
    from app.models.evidence_governance_models import OcrJob

    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    stmt = sa.select(OcrJob).where(OcrJob.id == jid, OcrJob.project_id == pid)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "job not found",
        )

    return _job_to_dict(job)


@router.post("/jobs/{job_id}/retry")
async def retry_ocr_job(
    project_id: str,
    year: int,
    job_id: str,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """重试失败的 OCR 任务（R5.3: 需 ocr.retry 能力）。

    P10: 越权重试零副作用。
    """
    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"ocr:retry:{job_id}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        retry_svc = OCRRetryService(txn.db)
        job = await retry_svc.retry_failed_job(
            job_id=jid,
            actor=txn.actor,
            actor_role=role,
            command_root_id=txn.command_root_id,
        )
        return job

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ocr.retry",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ocr.retry",
            object_type="ocr_job",
            object_id=jid,
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    job = cmd_result.result
    return {
        "job": _job_to_dict(job),
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/jobs/{job_id}/timeline")
async def get_job_timeline(
    project_id: str,
    year: int,
    job_id: str,
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """获取 OCR 任务的状态迁移时间线（R5.2: 保存每次状态迁移）。

    所有项目成员可访问。
    """
    import sqlalchemy as sa
    from app.models.evidence_governance_models import OcrJob, OcrJobTransition

    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Verify job belongs to this project
    job_stmt = sa.select(OcrJob.id).where(OcrJob.id == jid, OcrJob.project_id == pid)
    job_result = await db.execute(job_stmt)
    if job_result.scalar_one_or_none() is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "job not found",
        )

    # Fetch transitions ordered by creation time
    stmt = (
        sa.select(OcrJobTransition)
        .where(OcrJobTransition.ocr_job_id == jid)
        .order_by(OcrJobTransition.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    transitions = result.scalars().all()

    return {
        "job_id": str(jid),
        "transitions": [
            {
                "id": str(t.id),
                "from_state": t.from_state,
                "to_state": t.to_state,
                "actor_type": t.actor_type,
                "error_code": t.error_code,
                "error_message": t.error_message,
                "created_at": _isoformat(t.created_at),
            }
            for t in transitions
        ],
    }


@router.get("/jobs/{job_id}/results/{result_id}")
async def get_ocr_result(
    project_id: str,
    year: int,
    job_id: str,
    result_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """获取 OCR 结果详情（R6.1: 不可变 OCR_Result）。"""
    import sqlalchemy as sa
    from app.models.evidence_governance_models import OcrJob, OcrResult

    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    rid = _parse_uuid(result_id, "result_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Verify job scope
    job_stmt = sa.select(OcrJob.id).where(OcrJob.id == jid, OcrJob.project_id == pid)
    job_result = await db.execute(job_stmt)
    if job_result.scalar_one_or_none() is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "job not found",
        )

    # Fetch result
    stmt = sa.select(OcrResult).where(
        OcrResult.id == rid, OcrResult.ocr_job_id == jid
    )
    result = await db.execute(stmt)
    ocr_result = result.scalar_one_or_none()

    if ocr_result is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "result not found",
        )

    return {
        "id": str(ocr_result.id),
        "ocr_job_id": str(ocr_result.ocr_job_id),
        "raw_text": ocr_result.raw_text,
        "pages": ocr_result.pages,
        "fields": ocr_result.fields,
        "confidence": ocr_result.confidence,
        "engine": ocr_result.engine,
        "model_version": ocr_result.model_version,
        "config_version": ocr_result.config_version,
        "result_hash": ocr_result.result_hash,
        "created_at": _isoformat(ocr_result.created_at),
    }


@router.put("/jobs/{job_id}/results/{result_id}/confirmations")
async def add_confirmation(
    project_id: str,
    year: int,
    job_id: str,
    result_id: str,
    body: AddConfirmationRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """添加字段确认（R6.2: 人工确认 accepted/corrected/rejected）。

    ocr.confirm 能力 + 仅人工 actor（Service Identity 禁止确认）。
    """
    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    rid = _parse_uuid(result_id, "result_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Service Identity cannot confirm (R6.2 / design §2.2)
    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot perform human confirmation",
        )

    idem_key = idempotency_key or f"ocr:confirm:{result_id}:{body.field_name}:{body.decision}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = OCRConfirmationService(txn.db)
        confirmation = await svc.add_confirmation(
            result_id=rid,
            field_name=body.field_name,
            decision=body.decision,
            confirmed_value=body.confirmed_value,
            actor=txn.actor,
            reason=body.reason,
        )
        return confirmation

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ocr.confirm",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ocr.confirm",
            object_type="ocr_result",
            object_id=rid,
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    confirmation = cmd_result.result
    return {
        "id": str(confirmation.id),
        "result_id": str(confirmation.result_id),
        "field_name": confirmation.field_name,
        "decision": confirmation.decision,
        "confirmed_value": confirmation.confirmed_value,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/jobs/{job_id}/results/{result_id}/confirmations")
async def list_confirmations(
    project_id: str,
    year: int,
    job_id: str,
    result_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """列出 OCR 结果的所有确认记录（diff view）。"""
    import sqlalchemy as sa
    from app.models.evidence_governance_models import OcrConfirmation, OcrJob, OcrResult

    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    rid = _parse_uuid(result_id, "result_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Verify job scope
    job_stmt = sa.select(OcrJob.id).where(OcrJob.id == jid, OcrJob.project_id == pid)
    if (await db.execute(job_stmt)).scalar_one_or_none() is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "job not found",
        )

    # Fetch confirmations
    stmt = (
        sa.select(OcrConfirmation)
        .where(OcrConfirmation.result_id == rid)
        .order_by(OcrConfirmation.created_at.asc())
    )
    result = await db.execute(stmt)
    confirmations = result.scalars().all()

    return {
        "result_id": str(rid),
        "confirmations": [
            {
                "id": str(c.id),
                "field_name": c.field_name,
                "decision": c.decision,
                "original_value": c.original_value,
                "confirmed_value": c.confirmed_value,
                "actor_type": c.actor_type,
                "reason": c.reason,
                "created_at": _isoformat(c.created_at),
            }
            for c in confirmations
        ],
    }


@router.post("/jobs/{job_id}/results/{result_id}/writeback")
async def execute_writeback(
    project_id: str,
    year: int,
    job_id: str,
    result_id: str,
    body: ExecuteWritebackRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """执行 OCR 写回（R6.4: 原子提交全部字段）。

    需要 Idempotency-Key header。ocr.writeback 能力 + 仅人工 actor。
    版本冲突返回 409。
    """
    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    rid = _parse_uuid(result_id, "result_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    # Service Identity cannot writeback (design §2.2)
    if actor.actor_type.value == "service":
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "Service Identity cannot perform human writeback",
        )

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = OCRWritebackService(txn.db)
        wb_result = await svc.execute_writeback(
            job_id=jid,
            result_id=rid,
            target_type=body.target_type,
            target_id=body.target_id,
            target_version=body.target_version,
            actor=txn.actor,
            idempotency_key=idempotency_key,
        )
        return wb_result

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ocr.writeback",
            idempotency_key=idempotency_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="ocr.writeback",
            object_type="ocr_result",
            object_id=rid,
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    wb_result = cmd_result.result
    return {
        "writeback_id": str(wb_result.writeback_id),
        "status": wb_result.status,
        "fields_written": wb_result.fields_written,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/jobs/{job_id}/results/{result_id}/mapping")
async def preview_mapping(
    project_id: str,
    year: int,
    job_id: str,
    result_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """预览写回映射（确认前查看哪些字段会写入目标）。

    所有项目成员可访问。rejected 字段不出现在 mapping 中。
    """
    pid = _parse_uuid(project_id, "project_id")
    jid = _parse_uuid(job_id, "job_id")
    rid = _parse_uuid(result_id, "result_id")
    actor = ActorContext.for_user(current_user.id)
    role = await _get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    svc = OCRConfirmationService(db)
    mapping = await svc.build_mapping(rid)

    # Check all required decided
    all_decided = await svc.check_all_required_decided(rid)

    return {
        "result_id": str(rid),
        "mapping": mapping,
        "all_required_decided": all_decided,
        "ready_for_writeback": mapping is not None and all_decided,
    }
