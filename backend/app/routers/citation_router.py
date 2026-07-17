"""Citation Snapshot Router — 引用快照定位 API（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R7, R9, R15
Design: §5.3 RAG/AI, §4.6 Citation, §6.2 主要端点 (RAG/AI — citation locate row)
Properties: P15 (RAG 引用可定位), P16 (RAG 权限不扩张)
UAT: UAT-09（打开 citation 得到精确版本/page/region；来源被替换后旧 citation stale/invalid）

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/citations）：
  - GET  ``/``                    — 列出本 scope 的引用快照（只读，可按 ai_content_log_id 过滤）
  - GET  ``/{citation_id}/locate`` — 定位/打开引用（打开时重新鉴权，R7.3）
  - POST ``/validate``            — 批量校验引用集合（供 FormalOutput 门禁）

thin router：委托 ``CitationSnapshotService.locate_citation / validate_citation_set``，
不重写检索或权限逻辑；列表仅只读查询 ``citation_snapshots`` 表。CitationSnapshot 的
创建由 RAG 检索管线（create_citation_from_retrieval）在生成登记流程内完成，不在本 router
暴露独立创建端点（见文件尾 GAP 说明）。
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
from app.services.evidence_governance.citation_snapshot_service import (
    CitationSnapshotService,
    RetrievalCandidate,
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
    sha256_hex,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/citations",
    tags=["evidence-governance", "citation"],
)


class ValidateCitationsRequest(BaseModel):
    citation_ids: list[str] = Field(..., min_length=1)


class CreateCitationRequest(BaseModel):
    """注册引用快照（从已存在的活动 EvidenceRef 冻结）。

    这是 RAG/AI 生成登记管线在治理层的可达入口（design §5.3 检索候选 → CitationSnapshot；
    §10.2 允许测试专用 setup fixture 采证）。真实 RAG 检索也经同一
    ``CitationSnapshotService.create_citation_from_retrieval`` 过滤链（同 scope ∩ 可读 ∩
    active ref ∩ 版本/hash 有效 ∩ page/region 可定位），本端点不放宽任何过滤。
    """

    evidence_ref_id: str = Field(..., min_length=1)
    page: int = Field(..., ge=1)
    region: dict = Field(..., min_length=1)
    excerpt_text: str | None = None
    index_version: str | None = None
    locator_version: str | None = None
    # 可选：绑定已有 AiContentLog；缺省时创建最小 RAG 生成登记（user_id=当前人工 actor）。
    ai_content_log_id: str | None = None


@router.get("")
async def list_citations(
    project_id: str,
    year: int,
    ai_content_log_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """列出本 scope 的引用快照（只读）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    clauses = ["project_id = :pid", "(audit_year = :yr OR audit_year IS NULL)"]
    params: dict[str, Any] = {"pid": str(pid), "yr": year, "lim": limit}
    if ai_content_log_id:
        clauses.append("ai_content_log_id = :aid")
        params["aid"] = str(parse_uuid(ai_content_log_id, "ai_content_log_id"))

    rows = (
        await db.execute(
            sa.text(
                "SELECT id, ai_content_log_id, evidence_ref_id, audit_year, "
                "target_version, target_hash, page, region, excerpt_hash, "
                "index_version, locator_version, created_at "
                "FROM citation_snapshots WHERE " + " AND ".join(clauses) + " "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": str(r["id"]),
                "ai_content_log_id": str(r["ai_content_log_id"]),
                "evidence_ref_id": str(r["evidence_ref_id"]),
                "audit_year": r["audit_year"],
                "target_version": r["target_version"],
                "target_hash": r["target_hash"],
                "page": r["page"],
                "region": r["region"],
                "excerpt_hash": r["excerpt_hash"],
                "index_version": r["index_version"],
                "locator_version": r["locator_version"],
                "created_at": isoformat_or_none(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.post("", status_code=201)
async def create_citation(
    project_id: str,
    year: int,
    body: CreateCitationRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """注册引用快照（R7.1；capability ``ai.generate``）。

    委托 ``CitationSnapshotService.create_citation_from_retrieval`` —— 从一个已存在的活动
    ``EvidenceRef`` 冻结不可变 CitationSnapshot，保留精确 page/region/版本/hash（供 UAT-09
    打开定位）。过滤链任一项不满足（源不可读 / ref 非 active / 版本或 hash 失配 / page·region
    不可定位）→ 不创建快照并返回脱敏 422，绝不放宽 P15/P16。

    缺省 ``ai_content_log_id`` 时创建最小 RAG 生成登记（``ai_content_log``，user_id 为当前
    人工 actor）以满足 CitationSnapshot 的 AiContentLog 绑定契约（design §4.6）。
    """
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    ref_uuid = parse_uuid(body.evidence_ref_id, "evidence_ref_id")

    # 载入活动 EvidenceRef（同 scope）；不存在/非活动/越权 → 脱敏 404（不泄露目标信息）。
    ref_row = (
        await db.execute(
            sa.text(
                "SELECT id, evidence_type, evidence_id, target_version, target_hash "
                "FROM evidence_refs "
                "WHERE id = :rid AND project_id = :pid AND status = 'active' LIMIT 1"
            ),
            {"rid": str(ref_uuid), "pid": str(pid)},
        )
    ).mappings().first()
    if ref_row is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "evidence ref not found or not active",
        )

    # 缺省创建 ai_content_log 需要人工 actor（NOT NULL user_id）；service actor 必须显式传
    # ai_content_log_id。
    if body.ai_content_log_id is None and actor.actor_user_id is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.METADATA_INCOMPLETE,
            "ai_content_log_id required when actor has no user identity",
        )

    idem_key = idempotency_key or f"citation:create:{body.evidence_ref_id}:{body.page}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        # 1. 解析/创建 AiContentLog（CitationSnapshot.ai_content_log_id FK → ai_content_log）。
        if body.ai_content_log_id is not None:
            acl_id = parse_uuid(body.ai_content_log_id, "ai_content_log_id")
            exists = (
                await txn.db.execute(
                    sa.text(
                        "SELECT 1 FROM ai_content_log "
                        "WHERE id = :id AND project_id = :pid LIMIT 1"
                    ),
                    {"id": str(acl_id), "pid": str(pid)},
                )
            ).first()
            if exists is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "ai content log not found",
                )
        else:
            acl_id = uuid.uuid4()
            excerpt = body.excerpt_text or ""
            await txn.db.execute(
                sa.text(
                    "INSERT INTO ai_content_log "
                    "(id, project_id, user_id, content_hash, model, generated_content, "
                    " confirm_action, generated_at) "
                    "VALUES (:id, :pid, :uid, :ch, :model, :gen, 'pending', NOW())"
                ),
                {
                    "id": str(acl_id),
                    "pid": str(pid),
                    "uid": str(actor.actor_user_id),
                    "ch": sha256_hex(excerpt or str(acl_id)),
                    "model": "rag-citation",
                    "gen": excerpt or "(rag citation registration)",
                },
            )

        # 2. 经既有过滤链创建不可变 CitationSnapshot（不放宽 P15/P16）。
        candidate = RetrievalCandidate(
            source_type=ref_row["evidence_type"],
            source_id=ref_row["evidence_id"],
            source_version=(
                str(ref_row["target_version"])
                if ref_row["target_version"] is not None
                else None
            ),
            content_hash=ref_row["target_hash"],
            page=body.page,
            region=body.region,
            excerpt_text=body.excerpt_text,
            index_version=body.index_version,
            locator_version=body.locator_version,
            evidence_ref_id=ref_uuid,
        )
        svc = CitationSnapshotService(txn.db)
        created = await svc.create_citation_from_retrieval(
            retrieval_results=[candidate],
            actor=txn.actor,
            project_id=txn.project_id,
            audit_year=txn.audit_year or year,
            ai_content_log_id=acl_id,
        )
        if not created:
            # 过滤链拒绝（源不可读 / ref 非 active / 版本·hash 失配 / page·region 不可定位）。
            raise EvidenceGovernanceError(
                EvidenceErrorCode.METADATA_INCOMPLETE,
                "citation not locatable or source not readable/version-hash mismatch",
            )
        return {"citation": created[0], "ai_content_log_id": acl_id}

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="ai.citation.create",
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

    citation = cmd_result.result["citation"]
    return {
        "citation_id": str(citation.id),
        "evidence_ref_id": str(citation.evidence_ref_id),
        "ai_content_log_id": str(cmd_result.result["ai_content_log_id"]),
        "page": citation.page,
        "region": citation.region,
        "target_version": citation.source_version,
        "target_hash": citation.content_hash,
        "status": citation.status.value,
        "command_root_id": str(cmd_result.command_root_id),
    }


@router.get("/{citation_id}/locate")
async def locate_citation(
    project_id: str,
    year: int,
    citation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """定位/打开引用 — 打开时重新鉴权（R7.3 / P15）。

    来源不可读 / 版本或 hash 变更 / EvidenceRef 停用 → 返回 stale/invalid 状态（不抛错）。
    UAT-09。
    """
    pid = parse_uuid(project_id, "project_id")
    cid = parse_uuid(citation_id, "citation_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    svc = CitationSnapshotService(db)
    result = await svc.locate_citation(citation_id=cid, actor=actor, project_id=pid)

    return {
        "citation_id": str(result.citation_id),
        "status": result.status.value,
        "readable": result.readable,
        "version_valid": result.version_valid,
        "hash_valid": result.hash_valid,
        "source_available": result.source_available,
        "locator": result.locator,
        "page": result.page,
        "region": result.region,
        "reason": result.reason,
    }


@router.post("/validate")
async def validate_citations(
    project_id: str,
    year: int,
    body: ValidateCitationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """批量校验引用集合（供 FormalOutput 门禁；只读）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    cids = [parse_uuid(c, "citation_id") for c in body.citation_ids]

    svc = CitationSnapshotService(db)
    result = await svc.validate_citation_set(
        citation_ids=cids, actor=actor, project_id=pid
    )

    def _entries(entries: list[Any]) -> list[dict]:
        return [
            {"citation_id": str(e.citation_id), "status": e.status.value, "reason": e.reason}
            for e in entries
        ]

    return {
        "all_valid": result.all_valid,
        "valid": _entries(result.valid),
        "stale": _entries(result.stale),
        "invalid": _entries(result.invalid),
    }
