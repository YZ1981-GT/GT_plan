"""Archive Manifest Router — 归档清单与离线校验 API（Wave 9 HTTP 接线）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R11, R15
Design: §5.5 Archive/Retention/Legal Hold, §6.2 主要端点 (Archive/Hold row)
Properties: P23 (manifest 完备性), P24 (manifest 防覆盖)
UAT: UAT-12（缺 hash/stale/未确认 AI/OCR/Review 归档 → 仅验证失败阻断时生成完整
     blocking difference report；修复后新包离线 hash 通过且不生成阻断报告）

端点（前缀 /api/projects/{project_id}/years/{year}/evidence/archive）：
  - POST ``/preflight``                 — 归档前置门禁（冻结 watermark，不落库）
  - POST ``/manifests``                 — 构建/封存归档清单任务（archive.seal）
  - GET  ``/manifests``                 — 列出本 scope 的归档清单（只读）
  - GET  ``/manifests/{manifest_id}``   — 清单详情（含 entries/edges + 阻断差异报告）
  - POST ``/verify``                    — 离线校验提交的封存包（独立只读重算 hash）

thin router：构建流委托 ``ArchiveManifestService``（preflight / build_manifest / finalize），
离线校验委托 ``OfflineManifestVerifier``（不连接业务库，重算 member/manifest/package hash）。
成功封存 → 落 ``archive_manifests`` + entries + edges（state sealed，版本单调递增，P24）；
仅验证失败并实际阻断时才落 ``blocking_difference_report``（design §5.5）。
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
from app.services.evidence_governance.archive_manifest_service import (
    ArchiveManifestService,
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
from app.services.evidence_governance.offline_manifest_verifier import (
    OfflineManifestVerifier,
    serialize_sealed_package,
)
from app.services.evidence_governance.scope_guard import ProjectYearScopeGuard
from app.services.evidence_governance.unified_graph_builder import GraphScope

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/years/{year}/evidence/archive",
    tags=["evidence-governance", "archive"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────


class PreflightRequest(BaseModel):
    policy_version: str | None = None


class BuildManifestRequest(BaseModel):
    policy_version: str | None = None


class VerifyPackageRequest(BaseModel):
    package: dict = Field(..., description="序列化的封存包（SealedPackage dict）")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _split_node_key(node_key: str) -> tuple[str, str]:
    parts = node_key.split(":", 1)
    if len(parts) != 2:
        return ("unknown", node_key)
    return parts[0], parts[1]


async def _next_version(db: AsyncSession, pid: uuid.UUID, year: int) -> int:
    row = (
        await db.execute(
            sa.text(
                "SELECT COALESCE(MAX(version_no), 0) AS mx FROM archive_manifests "
                "WHERE project_id = :pid AND (audit_year = :yr OR audit_year IS NULL)"
            ),
            {"pid": str(pid), "yr": year},
        )
    ).mappings().first()
    return int(row["mx"]) + 1 if row else 1


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/preflight")
async def archive_preflight(
    project_id: str,
    year: int,
    body: PreflightRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """归档前置门禁（冻结 UnifiedGraph + policy 证据 watermark；只读，不落库）。"""
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    svc = ArchiveManifestService()
    scope = GraphScope(project_id=pid, audit_year=year)
    manifest = await svc.preflight(scope, actor, policy_version=body.policy_version)

    return {
        "watermark": manifest.watermark,
        "policy_version": manifest.policy_version,
        "phase": manifest.phase.value,
        "evidence_ready": manifest.phase.value != "failed",
    }


@router.post("/manifests", status_code=201)
async def build_manifest(
    project_id: str,
    year: int,
    body: BuildManifestRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """构建并封存归档清单（capability archive.seal；两阶段 watermark + P24 版本递增）。

    成功 → sealed 清单落库并返回序列化封存包（供离线校验）。
    验证失败并阻断 → 落 blocking_difference_report 并返回阻断差异（不封存）。
    """
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    idem_key = idempotency_key or f"archive:build:{pid}:{year}"

    facade = EvidenceGovernanceFacade(db)

    async def _business(txn: CommandTxn) -> Any:
        svc = ArchiveManifestService()
        scope = GraphScope(project_id=txn.project_id, audit_year=txn.audit_year or year)

        manifest = await svc.preflight(scope, actor, policy_version=body.policy_version)
        # 版本单调递增以 DB 为权威（P24）——覆盖服务内存版本
        manifest.version = await _next_version(txn.db, pid, txn.audit_year or year)
        manifest = await svc.build_manifest(manifest)
        result = await svc.finalize(manifest, actor)

        actor_cols = {
            "at": actor.actor_type.value,
            "auid": str(actor.actor_user_id) if actor.actor_user_id else None,
            "asid": (
                str(actor.actor_service_identity_id)
                if actor.actor_service_identity_id
                else None
            ),
        }

        manifest_row_id = uuid.uuid4()

        if result.success and result.sealed_package:
            pkg = result.sealed_package
            m = pkg.manifest
            await txn.db.execute(
                sa.text(
                    "INSERT INTO archive_manifests "
                    "(id, project_id, audit_year, version_no, watermark, policy_version, "
                    " package_hash, state, sealed_at, actor_type, actor_user_id, "
                    " actor_service_identity_id) "
                    "VALUES (:id, :pid, :yr, :ver, :wm, :pv, :ph, 'sealed', now(), "
                    " :at, :auid, :asid)"
                ),
                {
                    "id": str(manifest_row_id),
                    "pid": str(pid),
                    "yr": txn.audit_year or year,
                    "ver": m.version,
                    "wm": m.watermark or "",
                    "pv": m.policy_version,
                    "ph": pkg.package_hash,
                    **actor_cols,
                },
            )
            for e in m.entries:
                await txn.db.execute(
                    sa.text(
                        "INSERT INTO archive_manifest_entries "
                        "(id, archive_manifest_id, node_type, node_id, node_version, "
                        " node_hash, node_state) "
                        "VALUES (:id, :mid, :nt, :nid, :nv, :nh, :ns)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "mid": str(manifest_row_id),
                        "nt": e.entry_type.value,
                        "nid": e.object_id,
                        "nv": e.version,
                        "nh": e.content_hash,
                        "ns": e.state,
                    },
                )
            for edge in m.edges:
                s_type, s_id = _split_node_key(edge.source_key)
                t_type, t_id = _split_node_key(edge.target_key)
                await txn.db.execute(
                    sa.text(
                        "INSERT INTO archive_manifest_edges "
                        "(id, archive_manifest_id, source_type, source_id, target_type, "
                        " target_id, relation, edge_hash) "
                        "VALUES (:id, :mid, :st, :sid, :tt, :tid, :rel, :eh)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "mid": str(manifest_row_id),
                        "st": s_type,
                        "sid": s_id,
                        "tt": t_type,
                        "tid": t_id,
                        "rel": edge.provenance,
                        "eh": edge.edge_hash,
                    },
                )
            await txn.db.flush()
            return {
                "success": True,
                "manifest_id": str(manifest_row_id),
                "version": m.version,
                "state": "sealed",
                "package_hash": pkg.package_hash,
                "sealed_package": serialize_sealed_package(pkg),
            }

        # 阻断路径：落 building 状态 + blocking_difference_report（design §5.5）
        report = result.blocking_report
        report_json = report.to_machine_readable() if report else {}
        await txn.db.execute(
            sa.text(
                "INSERT INTO archive_manifests "
                "(id, project_id, audit_year, version_no, watermark, policy_version, "
                " state, blocking_difference_report, actor_type, actor_user_id, "
                " actor_service_identity_id) "
                "VALUES (:id, :pid, :yr, :ver, :wm, :pv, 'building', "
                " CAST(:rep AS JSONB), :at, :auid, :asid)"
            ),
            {
                "id": str(manifest_row_id),
                "pid": str(pid),
                "yr": txn.audit_year or year,
                "ver": manifest.version,
                "wm": manifest.watermark or "",
                "pv": manifest.policy_version,
                "rep": _json(report_json),
                **actor_cols,
            },
        )
        await txn.db.flush()
        return {
            "success": False,
            "manifest_id": str(manifest_row_id),
            "version": manifest.version,
            "state": "building",
            "blocked": True,
            "blocking_difference_report": report_json,
        }

    cmd_result = await facade.execute(
        CommandRequest(
            command_type="archive.seal",
            idempotency_key=idem_key,
            actor=actor,
            actor_role=role,
            project_id=pid,
            audit_year=year,
            capability="archive.seal",
        ),
        _business,
    )

    if cmd_result.replayed:
        return {"replayed": True, "command_root_id": str(cmd_result.command_root_id)}

    result = cmd_result.result
    result["command_root_id"] = str(cmd_result.command_root_id)
    return result


@router.get("/manifests")
async def list_manifests(
    project_id: str,
    year: int,
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """列出本 scope 的归档清单（只读）。"""
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
                "SELECT id, version_no, watermark, policy_version, package_hash, "
                "state, sealed_at, created_at, "
                "(blocking_difference_report IS NOT NULL) AS has_blocking_report "
                "FROM archive_manifests "
                "WHERE project_id = :pid AND (audit_year = :yr OR audit_year IS NULL) "
                "ORDER BY version_no DESC LIMIT :lim"
            ),
            {"pid": str(pid), "yr": year, "lim": limit},
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": str(r["id"]),
                "version_no": r["version_no"],
                "watermark": r["watermark"],
                "policy_version": r["policy_version"],
                "package_hash": r["package_hash"],
                "state": r["state"],
                "has_blocking_report": r["has_blocking_report"],
                "sealed_at": isoformat_or_none(r["sealed_at"]),
                "created_at": isoformat_or_none(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.get("/manifests/{manifest_id}")
async def get_manifest(
    project_id: str,
    year: int,
    manifest_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """清单详情（含 entries/edges；仅失败阻断时含 blocking_difference_report）。"""
    pid = parse_uuid(project_id, "project_id")
    mid = parse_uuid(manifest_id, "manifest_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    m = (
        await db.execute(
            sa.text(
                "SELECT id, version_no, watermark, policy_version, package_hash, state, "
                "blocking_difference_report, sealed_at, created_at "
                "FROM archive_manifests WHERE id = :mid AND project_id = :pid LIMIT 1"
            ),
            {"mid": str(mid), "pid": str(pid)},
        )
    ).mappings().first()
    if m is None:
        raise EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN, "manifest not found"
        )

    entries = (
        await db.execute(
            sa.text(
                "SELECT node_type, node_id, node_version, node_hash, node_state "
                "FROM archive_manifest_entries WHERE archive_manifest_id = :mid"
            ),
            {"mid": str(mid)},
        )
    ).mappings().all()
    edges = (
        await db.execute(
            sa.text(
                "SELECT source_type, source_id, target_type, target_id, relation, edge_hash "
                "FROM archive_manifest_edges WHERE archive_manifest_id = :mid"
            ),
            {"mid": str(mid)},
        )
    ).mappings().all()

    return {
        "id": str(m["id"]),
        "version_no": m["version_no"],
        "watermark": m["watermark"],
        "policy_version": m["policy_version"],
        "package_hash": m["package_hash"],
        "state": m["state"],
        "blocking_difference_report": m["blocking_difference_report"],
        "sealed_at": isoformat_or_none(m["sealed_at"]),
        "entries": [
            {
                "node_type": e["node_type"],
                "node_id": e["node_id"],
                "node_version": e["node_version"],
                "node_hash": e["node_hash"],
                "node_state": e["node_state"],
            }
            for e in entries
        ],
        "edges": [
            {
                "source_type": e["source_type"],
                "source_id": e["source_id"],
                "target_type": e["target_type"],
                "target_id": e["target_id"],
                "relation": e["relation"],
                "edge_hash": e["edge_hash"],
            }
            for e in edges
        ],
    }


@router.post("/verify")
async def verify_package(
    project_id: str,
    year: int,
    body: VerifyPackageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """离线校验封存包（R11；独立重算 member/manifest/package hash，不连业务库）。

    输入为构建端点返回的序列化封存包。校验失败时返回机器可读差异清单。
    """
    pid = parse_uuid(project_id, "project_id")
    actor = ActorContext.for_user(current_user.id)
    role = await get_user_role(db, current_user, pid)

    scope_guard = ProjectYearScopeGuard(db)
    await scope_guard.authorize_scope(
        actor_role=role, actor=actor, project_id=pid, audit_year=year
    )

    verifier = OfflineManifestVerifier()
    result = verifier.verify_package(body.package)
    return result.to_machine_readable()


def _json(obj: dict) -> str:
    import json as _j

    return _j.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
