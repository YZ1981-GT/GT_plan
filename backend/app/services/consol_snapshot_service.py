"""合并签字冻结服务 — Phase 2 P2（ADR-CONSOL-206 / 需求 8 / 属性 S8）

`create_snapshot` 端点原本只存 `{created_at}` 空壳（"框架在内容空"，P2）。本服务
把签字时刻的真实合并数据（consol_trial / worksheet / report / notes 全量结果）
序列化 + SHA-256 哈希 + base64+gzip 压缩后存入 `ConsolSnapshot.snapshot_data`，
实现签字冻结：

  - 5E.2 序列化全量数据 + 哈希 + 压缩存储（大数据 base64+gzip，EH8）
  - 5E.3 签字后锁定快照只读（`_locked` 标志）+ 还原"签字时合并数"对比
  - 5E.4 快照创建写审计留痕（复用 Phase 0 log_consol_action）

存储格式（`snapshot_data`）：
    {
      "_format": "gzip+base64",
      "_payload": "<base64(gzip(raw_json))>",
      "_hash":    "<sha256(raw_json) hex>",   # 压缩前的原始 JSON 哈希（S8 完整性）
      "_locked":  <bool>,                     # 签字锁定只读
      "_meta":    {counts, captured_sources, created_at, year}
    }

属性 S8（集成测试）：create_snapshot 后，即使子公司数据/抵销被改，从快照
反序列化能还原"签字时合并数"且哈希校验通过。

金额一律 `str(Decimal)` 序列化（避免 float 精度丢失，对比时精确相等）。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# reason 值落入这些时，快照创建即锁定为只读（签字冻结）
_LOCK_REASONS = {"sign", "signed", "lock", "locked", "signature"}

# 批 7 任务 7.2 / ADR-CRW-007 / R9.1~R9.2：sign/lock 快照的 required capturer。
# "required capturer 任一失败即拒绝" —— R9.2 列举的 required source 逐项映射到
# 这些 v2 分片（企业树 revision=tree、工作表 JSON/version=worksheet_data、分录及审批=entries、
# 差额表=worksheet_calc、试算=trial、报表 run=report、ConsolNoteData=consol_notes、
# 映射版本=mappings、公式版本=formulas、底稿复核/证据摘要+operation=lifecycle、
# artifact hash=artifact）。即 v2 的全部 11 类分片，任一分片采集失败则 sign/lock 拒绝。
# manual 快照不受此约束（可 partial，见 _build_v2_snapshot_data）。
#
# lifecycle 域"未创建签字快照"阻断文案（consol_readiness_service._lifecycle 同字面量）。
# sign/lock 门按本次正在创建快照的自引用豁免掉它，其余 lifecycle 阻断（复核退回等）仍生效。
_SNAPSHOT_SELF_BLOCKER = "未创建签字快照"

_SIGN_LOCK_REQUIRED_SHARDS: frozenset[str] = frozenset({
    "tree",
    "worksheet_data",
    "entries",
    "worksheet_calc",
    "trial",
    "report",
    "consol_notes",
    "mappings",
    "formulas",
    "lifecycle",
    "artifact",
})


class ConsolSnapshotRejected(Exception):
    """sign/lock 快照 fail-closed 拒绝（R9.1）：required source / readiness / artifact 任一失败。

    携带结构化拒绝原因，供路由层转成清晰的错误码/中文说明（不落库、不创建锁定快照）。

    Attributes:
        code: 机器可读拒绝码（``required_source_missing`` / ``readiness_not_ready`` /
            ``artifact_missing``；多类失败时取 ``sign_lock_gate_failed``）。
        message: 中文汇总说明。
        failures: 逐条失败明细 ``[{category, code, message, detail?}]``。
    """

    def __init__(self, code: str, message: str, failures: list[dict[str, Any]]):
        super().__init__(message)
        self.code = code
        self.message = message
        self.failures = failures

# 批 7 / ADR-CRW-007：v2 manifest 存储格式标识。
_FORMAT_V1 = "gzip+base64"
_FORMAT_V2 = "manifest-v2"

# ADR-CRW-007 的 11 类分片（顺序固定，根 hash 按此有序列表计算）。
# tree=企业树 revision/指纹，worksheet_data=工作表 JSON/version，entries=分录及审批，
# worksheet_calc=node×account 计算明细，trial=合并试算，report=根报表行，
# consol_notes=ConsolNoteData，mappings=映射规则/绑定，formulas=报表+附注公式版本，
# lifecycle=生命周期审计+operation terminal，artifact=不可变 artifact hash + report run。
_SHARD_ORDER: tuple[str, ...] = (
    "tree",
    "worksheet_data",
    "entries",
    "worksheet_calc",
    "trial",
    "report",
    "consol_notes",
    "mappings",
    "formulas",
    "lifecycle",
    "artifact",
)


# ---------------------------------------------------------------------------
# 序列化 + 哈希 + 压缩（EH8）
# ---------------------------------------------------------------------------

def _canonical_json(raw: dict[str, Any]) -> str:
    """规范化 JSON 序列化：sort_keys 保证哈希可复现，default=str 兜底 Decimal/UUID/datetime。"""
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compress_payload(raw_json: str) -> str:
    """base64+gzip 压缩原始 JSON（EH8，镜像 wp_offline _meta_ 模式）。"""
    return base64.b64encode(gzip.compress(raw_json.encode("utf-8"))).decode("ascii")


def _decompress_payload(encoded: str) -> str:
    """base64+gunzip 还原原始 JSON 字符串。"""
    return gzip.decompress(base64.b64decode(encoded.encode("ascii"))).decode("utf-8")


# ---------------------------------------------------------------------------
# 各数据源采集（每个独立 try/except，记录 captured_sources，单源失败不影响整体）
# ---------------------------------------------------------------------------

async def _capture_trial(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """采集 consol_trial 全量行（含 consolidation_breakdown provenance）。"""
    from app.models.consolidation_models import ConsolTrial

    result = await db.execute(
        sa.select(ConsolTrial).where(
            ConsolTrial.project_id == project_id,
            ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(),
        )
    )
    rows: list[dict] = []
    for t in result.scalars().all():
        rows.append({
            "standard_account_code": t.standard_account_code,
            "account_name": t.account_name,
            "account_category": t.account_category.value if t.account_category else None,
            "individual_sum": str(t.individual_sum),
            "consol_adjustment": str(t.consol_adjustment),
            "consol_elimination": str(t.consol_elimination),
            "consol_amount": str(t.consol_amount),
            "consolidation_breakdown": t.consolidation_breakdown,
        })
    return rows


async def _capture_worksheet(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """采集 consol_worksheet 全量行（node × account 明细）。"""
    from app.models.consolidation_models import ConsolWorksheet

    result = await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )
    rows: list[dict] = []
    for w in result.scalars().all():
        rows.append({
            "node_company_code": w.node_company_code,
            "account_code": w.account_code,
            "adjustment_debit": str(w.adjustment_debit),
            "adjustment_credit": str(w.adjustment_credit),
            "elimination_debit": str(w.elimination_debit),
            "elimination_credit": str(w.elimination_credit),
            "net_difference": str(w.net_difference),
            "children_amount_sum": str(w.children_amount_sum),
            "consolidated_amount": str(w.consolidated_amount),
        })
    return rows


async def _capture_report(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """采集 financial_report 全量行。"""
    from app.models.report_models import FinancialReport

    result = await db.execute(
        sa.select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    rows: list[dict] = []
    for r in result.scalars().all():
        rows.append({
            "report_type": r.report_type.value if r.report_type else None,
            "row_code": r.row_code,
            "row_name": r.row_name,
            "current_period_amount": str(r.current_period_amount) if r.current_period_amount is not None else None,
            "prior_period_amount": str(r.prior_period_amount) if r.prior_period_amount is not None else None,
        })
    return rows


async def _capture_notes(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """采集 disclosure_notes 全量行（合并附注章节）。"""
    from app.models.report_models import DisclosureNote

    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    rows: list[dict] = []
    for n in result.scalars().all():
        rows.append({
            "note_section": n.note_section,
            "section_id": n.section_id,
            "section_title": n.section_title,
            "table_data": n.table_data,
            "text_content": n.text_content,
        })
    return rows


async def _capture_tree(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """分片 tree：活跃企业树范围确认的 revision + 指纹（R9.2 企业树 revision）。"""
    from app.models.consol_scope_confirmation_models import ConsolScopeConfirmation

    row = (await db.execute(
        sa.select(
            ConsolScopeConfirmation.revision,
            ConsolScopeConfirmation.fingerprint,
            ConsolScopeConfirmation.status,
        ).where(
            ConsolScopeConfirmation.project_id == project_id,
            ConsolScopeConfirmation.year == year,
            ConsolScopeConfirmation.status == "active",
        ).order_by(ConsolScopeConfirmation.revision.desc())
    )).first()
    if row is None:
        return {}
    return {
        "revision": int(row.revision) if row.revision is not None else None,
        "fingerprint": row.fingerprint,
        "status": row.status,
    }


async def _capture_worksheet_data(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """分片 worksheet_data：工作表 JSON 与 version（R9.2 工作表 JSON/version）。"""
    from app.models.consol_worksheet_data_models import ConsolWorksheetData

    result = await db.execute(
        sa.select(ConsolWorksheetData).where(
            ConsolWorksheetData.project_id == project_id,
            ConsolWorksheetData.year == year,
        ).order_by(ConsolWorksheetData.sheet_key)
    )
    return [
        {
            "sheet_key": w.sheet_key,
            "version": int(w.version or 0),
            "data": w.data,
        }
        for w in result.scalars().all()
    ]


async def _capture_entries(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """分片 entries：抵销/调整分录及审批状态（R9.2 分录及审批）。"""
    from app.models.consolidation_models import EliminationEntry

    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
        ).order_by(EliminationEntry.entry_no, EliminationEntry.id)
    )
    rows: list[dict] = []
    for e in result.scalars().all():
        rows.append({
            "id": str(e.id),
            "entry_no": e.entry_no,
            "entry_type": e.entry_type.value if e.entry_type else None,
            "entry_group_id": str(e.entry_group_id) if e.entry_group_id else None,
            "account_code": e.account_code,
            "branch_entity_code": e.branch_entity_code,
            "debit_amount": str(e.debit_amount),
            "credit_amount": str(e.credit_amount),
            "lines": e.lines,
            "review_status": e.review_status.value if e.review_status else None,
            "source_version": e.source_version,
            "source_digest": e.source_digest,
        })
    return rows


async def _capture_consol_notes(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """分片 consol_notes：ConsolNoteData 全量（R9.2 ConsolNoteData）。"""
    from app.models.consol_note_data_models import ConsolNoteData

    result = await db.execute(
        sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == project_id,
            ConsolNoteData.year == year,
        ).order_by(ConsolNoteData.section_id, ConsolNoteData.node_key)
    )
    rows: list[dict] = []
    for n in result.scalars().all():
        rows.append({
            "section_id": n.section_id,
            "node_key": n.node_key,
            "data": n.data,
            "is_stale": bool(n.is_stale),
            "cell_state": n.cell_state,
            "locked_cells": n.locked_cells,
            "source_mode": n.source_mode,
            "source_operation_id": str(n.source_operation_id) if n.source_operation_id else None,
            "source_revision": n.source_revision,
            "source_digest": n.source_digest,
        })
    return rows


async def _capture_mappings(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """分片 mappings：附注映射模板绑定/规则/企业绑定版本（R9.2 映射版本）。"""
    from app.models.consol_note_mapping_models import (
        ConsolNoteMappingBinding,
        ConsolNoteMappingRule,
        ConsolNoteTemplateBinding,
    )

    template_bindings = (await db.execute(
        sa.select(
            ConsolNoteTemplateBinding.section_id,
            ConsolNoteTemplateBinding.template_version_id,
        ).where(ConsolNoteTemplateBinding.project_id == project_id)
        .order_by(ConsolNoteTemplateBinding.section_id)
    )).all()
    rules = (await db.execute(
        sa.select(
            ConsolNoteMappingRule.id,
            ConsolNoteMappingRule.section_id,
            ConsolNoteMappingRule.template_version_id,
            ConsolNoteMappingRule.source_structure_hash,
            ConsolNoteMappingRule.version_number,
        ).where(
            ConsolNoteMappingRule.project_id == project_id,
            ConsolNoteMappingRule.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRule.section_id, ConsolNoteMappingRule.id)
    )).all()
    bindings = (await db.execute(
        sa.select(
            ConsolNoteMappingBinding.section_id,
            ConsolNoteMappingBinding.entity_node_key,
            ConsolNoteMappingBinding.rule_id,
            ConsolNoteMappingBinding.bound_source_hash,
            ConsolNoteMappingBinding.status,
        ).where(ConsolNoteMappingBinding.project_id == project_id)
        .order_by(ConsolNoteMappingBinding.section_id, ConsolNoteMappingBinding.entity_node_key)
    )).all()
    return {
        "template_bindings": [
            {"section_id": s, "template_version_id": str(v) if v else None}
            for s, v in template_bindings
        ],
        "rules": [
            {
                "id": str(rid),
                "section_id": sid,
                "template_version_id": str(tv) if tv else None,
                "source_structure_hash": ssh,
                "version_number": vn,
            }
            for rid, sid, tv, ssh, vn in rules
        ],
        "bindings": [
            {
                "section_id": sid,
                "entity_node_key": nk,
                "rule_id": str(rid) if rid else None,
                "bound_source_hash": bsh,
                "status": status,
            }
            for sid, nk, rid, bsh, status in bindings
        ],
    }


async def _capture_formulas(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """分片 formulas：报表 + 附注公式版本（R9.2 公式版本）。

    模板级公式按合并口径读取（report=`{tt}_consolidated`，note=template_type）。
    template_type 以活跃范围确认推断不出时默认 soe（与版本向量同口径）。
    """
    from app.models.consol_push_models import ConsolNoteFormula
    from app.models.report_models import ReportConfig

    from app.models.core import Project

    template_type = "soe"
    try:
        tt = (await db.execute(
            sa.select(Project.template_type).where(Project.id == project_id)
        )).scalar_one_or_none()
        if tt:
            template_type = tt
    except Exception:  # noqa: BLE001 — 推断失败回落 soe，不阻断快照
        pass

    standard = f"{template_type}_consolidated"
    report_formulas = (await db.execute(
        sa.select(
            ReportConfig.report_type,
            ReportConfig.row_code,
            ReportConfig.formula,
            ReportConfig.formula_version,
        ).where(
            ReportConfig.applicable_standard == standard,
            ReportConfig.is_deleted == sa.false(),
        ).order_by(ReportConfig.report_type, ReportConfig.row_code)
    )).all()
    note_formulas = (await db.execute(
        sa.select(
            ConsolNoteFormula.section_id,
            ConsolNoteFormula.row_index,
            ConsolNoteFormula.col_index,
            ConsolNoteFormula.formula,
            ConsolNoteFormula.version,
        ).where(
            ConsolNoteFormula.template_type == template_type,
            ConsolNoteFormula.is_deleted == sa.false(),
        ).order_by(
            ConsolNoteFormula.section_id,
            ConsolNoteFormula.row_index,
            ConsolNoteFormula.col_index,
        )
    )).all()
    return {
        "template_type": template_type,
        "report": [
            {"report_type": rt, "row_code": rc, "formula": f, "formula_version": fv}
            for rt, rc, f, fv in report_formulas
        ],
        "note": [
            {"section_id": sid, "row_index": ri, "col_index": ci, "formula": f, "version": v}
            for sid, ri, ci, f, v in note_formulas
        ],
    }


async def _capture_lifecycle(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """分片 lifecycle：生命周期审计留痕摘要 + 最近正式 operation terminal（R9.2 复核/证据摘要 + operation）。"""
    from app.models.consol_operation_models import ConsolOperation

    operation = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "succeeded",
        ).order_by(ConsolOperation.finished_at.desc()).limit(1)
    )).scalar_one_or_none()

    # 审计留痕哈希链按 project chain_key 追加（无 project_id 列）；与归档 provider 同口径，
    # 仅按 action_type 前缀 consol.* 过滤本模块生命周期留痕，取链尾 hash 作可追溯凭据。
    audit_rows: list[dict] = []
    tail_hash: str | None = None
    try:
        from app.models.audit_log_models import AuditLogEntry

        rows = (await db.execute(
            sa.select(
                AuditLogEntry.id,
                AuditLogEntry.action_type,
                AuditLogEntry.object_type,
                AuditLogEntry.object_id,
                AuditLogEntry.entry_hash,
                AuditLogEntry.ts,
            ).where(
                AuditLogEntry.action_type.like("consol.%"),
            ).order_by(AuditLogEntry.ts)
        )).all()
        for aid, action, otype, oid, entry_hash, ts in rows:
            audit_rows.append({
                "id": str(aid),
                "action_type": action,
                "object_type": otype,
                "object_id": str(oid) if oid else None,
                "entry_hash": entry_hash,
                "ts": ts.isoformat() if ts else None,
            })
        if audit_rows:
            tail_hash = audit_rows[-1]["entry_hash"]
    except Exception as exc:  # noqa: BLE001 — 审计表读取失败只记空摘要，不阻断
        logger.warning("ConsolSnapshot lifecycle 审计摘要读取失败：%s", exc)

    return {
        "operation": None if operation is None else {
            "id": str(operation.id),
            "revision": operation.revision,
            "status": operation.status,
            "request_hash": operation.request_hash,
            "finished_at": operation.finished_at.isoformat() if operation.finished_at else None,
        },
        "audit_count": len(audit_rows),
        "audit_tail_hash": tail_hash,
        "audit_entries": audit_rows,
    }


async def _capture_artifact(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """分片 artifact：不可变 artifact hash + report run（R9.2 artifact hash + 报表 run）。"""
    from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun

    artifacts = (await db.execute(
        sa.select(
            ConsolArtifact.id,
            ConsolArtifact.report_run_id,
            ConsolArtifact.operation_id,
            ConsolArtifact.node_key,
            ConsolArtifact.kind,
            ConsolArtifact.status,
            ConsolArtifact.sha256,
            ConsolArtifact.size_bytes,
            ConsolArtifact.file_name,
        ).where(
            ConsolArtifact.project_id == project_id,
            ConsolArtifact.year == year,
            ConsolArtifact.status == "ready",
        ).order_by(ConsolArtifact.report_run_id, ConsolArtifact.kind, ConsolArtifact.node_key)
    )).all()

    runs = (await db.execute(
        sa.select(
            ReportGenerationRun.id,
            ReportGenerationRun.operation_id,
            ReportGenerationRun.status,
            ReportGenerationRun.calc_version,
        ).where(
            ReportGenerationRun.project_id == project_id,
            ReportGenerationRun.year == year,
        ).order_by(ReportGenerationRun.finished_at.desc().nullslast()).limit(20)
    )).all()

    return {
        "artifacts": [
            {
                "id": str(aid),
                "report_run_id": str(rrid) if rrid else None,
                "operation_id": str(oid) if oid else None,
                "node_key": nk,
                "kind": kind,
                "status": status,
                "sha256": sha,
                "size_bytes": sz,
                "file_name": fn,
            }
            for aid, rrid, oid, nk, kind, status, sha, sz, fn in artifacts
        ],
        "report_runs": [
            {
                "id": str(rid),
                "operation_id": str(oid) if oid else None,
                "status": status,
                "calc_version": cv,
            }
            for rid, oid, status, cv in runs
        ],
    }


# v1 兼容数据源采集器注册表：(键, 采集函数)。旧 `create_consol_snapshot(..., format_version=1)`
# 或历史快照仍可回落到这组字段（trial/worksheet/report/notes）。
_CAPTURERS: tuple[tuple[str, Any], ...] = (
    ("trial", _capture_trial),
    ("worksheet", _capture_worksheet),
    ("report", _capture_report),
    ("notes", _capture_notes),
)

# v2 manifest 分片采集器：键必须覆盖 `_SHARD_ORDER`（11 类）。
_SHARD_CAPTURERS: dict[str, Any] = {
    "tree": _capture_tree,
    "worksheet_data": _capture_worksheet_data,
    "entries": _capture_entries,
    "worksheet_calc": _capture_worksheet,
    "trial": _capture_trial,
    "report": _capture_report,
    "consol_notes": _capture_consol_notes,
    "mappings": _capture_mappings,
    "formulas": _capture_formulas,
    "lifecycle": _capture_lifecycle,
    "artifact": _capture_artifact,
}


# ---------------------------------------------------------------------------
# v2 manifest：分片 hash + 根 hash + operation/version refs（ADR-CRW-007 / R9.3）
# ---------------------------------------------------------------------------

def _shard_hash(shard_value: Any) -> str:
    """单个分片的 canonical JSON 的 SHA-256（分片 hash）。"""
    return _sha256_hex(_canonical_json(shard_value))


def _root_hash(shard_hashes: dict[str, str]) -> str:
    """对有序 (shard_key, shard_hash) 列表再计算根 hash（manifest 根 hash）。

    顺序固定为 `_SHARD_ORDER`，只纳入实际捕获的分片键，保证可复现。
    """
    ordered = [
        [key, shard_hashes[key]]
        for key in _SHARD_ORDER
        if key in shard_hashes
    ]
    return _sha256_hex(_canonical_json(ordered))


def _build_v2_manifest(
    shards: dict[str, Any],
    shard_hashes: dict[str, str],
    *,
    captured_sources: list[str],
    failed_sources: list[str],
    operation_ref: dict[str, Any] | None,
    version_ref: dict[str, Any] | None,
    partial: bool,
) -> dict[str, Any]:
    """组装 v2 manifest（不含压缩 payload；payload 由调用方压缩 raw 分片数据）。"""
    counts: dict[str, int] = {}
    for key, value in shards.items():
        if isinstance(value, (list, tuple)):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value)
        else:
            counts[key] = 0
    return {
        "manifest_version": 2,
        "shard_order": list(_SHARD_ORDER),
        "shard_hashes": shard_hashes,
        "root_hash": _root_hash(shard_hashes),
        "counts": counts,
        "captured_sources": captured_sources,
        "failed_sources": failed_sources,
        "partial": partial,
        "operation_ref": operation_ref or {},
        "version_ref": version_ref or {},
    }


def _manifest_operation_ref(lifecycle_shard: Any) -> dict[str, Any]:
    """从 lifecycle 分片提取最近成功 operation 引用（operation refs）。"""
    if not isinstance(lifecycle_shard, dict):
        return {}
    operation = lifecycle_shard.get("operation")
    if not isinstance(operation, dict):
        return {}
    return {
        "operation_id": operation.get("id"),
        "revision": operation.get("revision"),
        "status": operation.get("status"),
        "request_hash": operation.get("request_hash"),
    }


def _manifest_version_ref(operation: Any) -> dict[str, Any]:
    """从最近成功 operation 的 version_vector 提取版本摘要（version refs）。

    复用批 2 已持久化的 `ConsolOperation.version_vector`，不重算企业树/版本向量。
    """
    if operation is None:
        return {}
    vector = dict(getattr(operation, "version_vector", {}) or {})
    if not vector:
        return {}
    return {
        "digest": vector.get("digest"),
        "tree_fingerprint": vector.get("tree_fingerprint"),
        "tree_revision": vector.get("tree_revision"),
        "tb_digest": vector.get("tb_digest"),
        "elimination_digest": vector.get("elimination_digest"),
        "formula_digest": vector.get("formula_digest"),
        "note_mapping_digest": vector.get("note_mapping_digest"),
        "template_digest": vector.get("template_digest"),
    }


async def _latest_succeeded_operation(db: AsyncSession, project_id: UUID, year: int):
    """取最近一次成功 operation（供 version refs；无则 None）。"""
    from app.models.consol_operation_models import ConsolOperation

    return (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "succeeded",
        ).order_by(ConsolOperation.finished_at.desc()).limit(1)
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# sign/lock 政策门（ADR-CRW-007 / R9.1~R9.2）：required source / readiness / artifact
# ---------------------------------------------------------------------------


def _is_lock_reason(reason: str, lock: bool | None) -> bool:
    """判断本次是否属签字/锁定（fail-closed）口径。

    显式 ``lock=True`` 一律按 sign/lock；``lock=False`` 一律按 manual（显式覆盖）；
    ``lock=None`` 按 ``reason`` 推断（落在 ``_LOCK_REASONS`` 为 sign/lock）。
    """
    if lock is True:
        return True
    if lock is False:
        return False
    return reason.lower() in _LOCK_REASONS


async def evaluate_sign_lock_gate(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    failed_shards: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """评估 sign/lock 快照 fail-closed 门（R9.1）：三类 required 检查全过才放行。

    复用既有真源，不重建 readiness / artifact 逻辑：
      (a) required source —— ``failed_shards`` 与 ``_SIGN_LOCK_REQUIRED_SHARDS`` 有交集即失败；
          ``failed_shards`` 由 v2 分片采集阶段产出（None 时视为"尚未采集"，仅跳过本检查）。
      (b) readiness —— 复用 :func:`consol_readiness_service.load_readiness_facts` +
          ``build_readiness``（不重算），任一域 ``not_ready`` 即失败；但剔除 lifecycle 的
          "未创建签字快照"自引用阻断（本次正要创建它，鸡生蛋豁免）。
      (c) artifact —— 复用 :func:`consol_archive_provider.collect_consol_archive_items`
          的 report_run + 两 artifact 项，任一 ``missing`` 即失败。

    Returns:
        ``{"allowed": bool, "failures": [{category, code, message, detail?}], "readiness": {...}}``
        （只评估不抛错；是否抛 :class:`ConsolSnapshotRejected` 由调用方按 allowed 决定。）
    """
    failures: list[dict[str, Any]] = []

    # (a) required source 捕获完整性 -----------------------------------------
    if failed_shards:
        missing_required = sorted(set(failed_shards) & _SIGN_LOCK_REQUIRED_SHARDS)
        if missing_required:
            failures.append({
                "category": "required_source",
                "code": "required_source_missing",
                "message": "签字/锁定快照要求采集全部 required 分片，以下分片采集失败："
                + "、".join(missing_required),
                "detail": {"failed_required_shards": missing_required},
            })

    # (b) readiness 必须就绪（复用七域 readiness，不重算）------------------------
    # 自引用豁免：lifecycle 域的"未创建签字快照"阻断正是本次要创建的对象，纳入会使签字
    # 永远无法通过（鸡生蛋），故在门内剔除该条；lifecycle 的复核退回等其余阻断仍生效。
    readiness: dict[str, Any] = {}
    try:
        from app.services.consol_readiness_service import (
            build_readiness,
            load_readiness_facts,
            readiness_payload,
        )

        facts = await load_readiness_facts(db, project_id, year)
        domains = build_readiness(facts)
        readiness = readiness_payload(domains)
    except Exception as exc:  # noqa: BLE001 — readiness 读取失败本身即阻断（fail-closed）
        logger.warning("sign/lock 门 readiness 读取失败（项目=%s 年度=%s）：%s", project_id, year, exc)
        failures.append({
            "category": "readiness",
            "code": "readiness_unavailable",
            "message": "无法确认合并 readiness 状态，签字/锁定已拒绝",
            "detail": {"error": str(exc)[:200]},
        })
    else:
        gate_blockers = [
            str(b)
            for d in domains
            if d.status == "not_ready"
            for b in d.blockers
            if b != _SNAPSHOT_SELF_BLOCKER
        ]
        if gate_blockers:
            failures.append({
                "category": "readiness",
                "code": "readiness_not_ready",
                "message": "合并 readiness 未就绪，签字/锁定已拒绝：" + "；".join(gate_blockers[:8]),
                "detail": {"blockers": gate_blockers, "status": readiness.get("status")},
            })

    # (c) artifact 必须齐备（复用归档 provider 的 report_run + artifact 判定）--------
    try:
        from app.services.consol_archive_provider import collect_consol_archive_items

        # require_snapshot=False：本门正处在创建签字快照的前置阶段，快照尚未落库；
        # 只取 report_run + report_excel + consol_workpaper 三个 artifact 判定，
        # 不把"尚不存在的签字快照"算成缺件（避免鸡生蛋）。
        items = await collect_consol_archive_items(
            db, project_id, year, require_snapshot=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sign/lock 门 artifact 读取失败（项目=%s 年度=%s）：%s", project_id, year, exc)
        failures.append({
            "category": "artifact",
            "code": "artifact_unavailable",
            "message": "无法确认合并 artifact 完整性，签字/锁定已拒绝",
            "detail": {"error": str(exc)[:200]},
        })
    else:
        artifact_kinds = {"consol_operation", "report_run", "report_excel", "consol_workpaper"}
        missing_artifacts = [
            {"kind": item["kind"], "label": item.get("label"), "reason": item.get("reason")}
            for item in items
            if item.get("kind") in artifact_kinds and item.get("status") == "missing"
        ]
        if missing_artifacts:
            labels = "、".join(str(m.get("label") or m["kind"]) for m in missing_artifacts)
            failures.append({
                "category": "artifact",
                "code": "artifact_missing",
                "message": "签字/锁定快照要求正式报表运行与不可变 artifact 齐备，以下缺失："
                + labels,
                "detail": {"missing": missing_artifacts},
            })

    return {"allowed": not failures, "failures": failures, "readiness": readiness}


def _reject_code(failures: list[dict[str, Any]]) -> str:
    """多类失败时的汇总拒绝码；单类失败直接用该类的 code。"""
    if len(failures) == 1:
        return str(failures[0]["code"])
    return "sign_lock_gate_failed"


# ---------------------------------------------------------------------------
# 创建快照（5E.2 + 5E.4）
# ---------------------------------------------------------------------------

async def create_consol_snapshot(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    reason: str = "manual",
    *,
    user_id: UUID | None = None,
    lock: bool | None = None,
    format_version: int = 2,
    enforce_gate: bool = True,
) -> dict:
    """采集签字时刻全量合并数据 → 分片 hash → 根 hash → 压缩 → 存 ConsolSnapshot。

    默认写 v2 manifest（ADR-CRW-007 / R9.3）：11 类分片各自 canonical JSON + SHA-256，
    manifest 对有序分片 hash 再计算根 hash，并附最近成功 operation 与版本向量摘要。
    根 hash 复用 `_hash` 字段，归档 provider 据此校验完整性（v1/v2 同口径）。

    Args:
        db: 异步会话
        project_id: 合并母项目 ID
        year: 年度
        reason: 触发原因（sign/signed/lock 等会令快照锁定只读）
        user_id: 操作人（审计留痕用）
        lock: 显式锁定标志；None 时按 reason 推断（签字类原因→锁定）
        format_version: 2=v2 manifest（默认）；1=旧 gzip+base64 兼容格式
        enforce_gate: True（默认，生产/签字路由口径）时 sign/lock 走 fail-closed 门；
            False 仅用于下游测试构造已锁定快照 fixture（显式绕过门，不在生产路径使用）

    Returns:
        {"id", "year", "hash"(根 hash), "locked", "meta", "manifest"(v2 时)}

    manual 快照单源采集失败不阻断：记录 captured_sources/failed_sources（v2 时 partial=True）。
    sign/lock 快照（reason∈_LOCK_REASONS 或 lock=True）fail-closed（R9.1，任务 7.2）：
    required 分片采集失败 / readiness 未就绪 / 正式报表运行或 artifact 缺失，任一发生即抛
    :class:`ConsolSnapshotRejected` 且不落库（不 add/flush/commit）。
    审计留痕失败不破坏快照创建（try/except + warning）。

    事务边界（任务 7.3 / ADR-CRW-007 / design §49-51）：本服务**只 flush 不 commit**。
    flush 取 snap.id 并在同一会话可见；commit 由调用方（签字路由）负责，使快照、签字记录、
    operation terminal 和 consol_lock 落在同一事务边界，任一失败整体回滚（all-or-nothing）。
    """
    from app.models.phase10_models import ConsolSnapshot

    if format_version == 1:
        snapshot_data, result = await _build_v1_snapshot_data(db, project_id, year, reason, lock)
    else:
        snapshot_data, result = await _build_v2_snapshot_data(db, project_id, year, reason, lock)

    # sign/lock fail-closed 门（任务 7.2 / R9.1）：在落库前评估 required source /
    # readiness / artifact，任一失败则拒绝，绝不持久化锁定快照（manual 口径不走此门）。
    if enforce_gate and _is_lock_reason(reason, lock):
        failed_shards = result.get("meta", {}).get("failed_sources") or []
        gate = await evaluate_sign_lock_gate(
            db, project_id, year, failed_shards=failed_shards,
        )
        if not gate["allowed"]:
            failures = gate["failures"]
            raise ConsolSnapshotRejected(
                code=_reject_code(failures),
                message="签字/锁定快照被拒绝（完整性/就绪度未满足）："
                + "；".join(f["message"] for f in failures),
                failures=failures,
            )

    snap = ConsolSnapshot(
        project_id=project_id,
        year=year,
        snapshot_data=snapshot_data,
        trigger_reason=reason[:30],
        created_by=user_id,
    )
    db.add(snap)
    await db.flush()  # 取 snap.id；commit 由路由层负责（与审计留痕同事务）

    # 审计留痕（复用 Phase 0 log_consol_action）；失败不破坏快照创建
    if user_id is not None:
        try:
            from app.services.consol_audit_helper import log_consol_action

            await log_consol_action(
                db,
                user_id=user_id,
                project_id=project_id,
                action="consol.snapshot.create",
                resource_type="consol_snapshot",
                resource_id=str(snap.id),
                before=None,
                after={
                    "hash": result["hash"],
                    "locked": result["locked"],
                    "reason": reason,
                    "counts": result["meta"].get("counts"),
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ConsolSnapshot 审计留痕失败（快照 %s 仍创建）：%s", snap.id, e)

    # 批 7 任务 7.3 / ADR-CRW-007（design §49-51「snapshot 创建只 flush，签字路由统一提交」）：
    # 本服务只 flush 取 id，绝不 commit。commit 由调用方（签字路由）负责，使 snapshot、
    # 签字记录、operation terminal 和 consol_lock 落在同一事务边界，任一失败整体回滚。
    result["id"] = str(snap.id)
    return result


async def _build_v1_snapshot_data(
    db: AsyncSession, project_id: UUID, year: int, reason: str, lock: bool | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """旧 gzip+base64 格式（整体一个 hash），用于兼容回退与历史口径。"""
    captured_sources: list[str] = []
    # v1 源键→v2 required 分片名，使 sign/lock 门按统一的 required 集合判定（trial/worksheet/
    # report/notes 皆属 required：worksheet→worksheet_calc、notes→consol_notes）。
    _v1_to_required = {
        "trial": "trial",
        "worksheet": "worksheet_calc",
        "report": "report",
        "notes": "consol_notes",
    }
    failed_sources: list[str] = []
    raw: dict[str, Any] = {
        "project_id": str(project_id),
        "year": year,
        "_captured_at": datetime.now(timezone.utc).isoformat(),
    }
    counts: dict[str, int] = {}
    for key, capturer in _CAPTURERS:
        try:
            rows = await capturer(db, project_id, year)
            raw[key] = rows
            counts[key] = len(rows)
            captured_sources.append(key)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "ConsolSnapshot 采集数据源 %s 失败（项目=%s 年度=%s）：%s", key, project_id, year, e,
            )
            raw[key] = []
            counts[key] = 0
            failed_sources.append(_v1_to_required.get(key, key))

    raw_json = _canonical_json(raw)
    sha = _sha256_hex(raw_json)
    payload_b64 = _compress_payload(raw_json)
    locked = lock if lock is not None else (reason.lower() in _LOCK_REASONS)
    meta = {
        "counts": counts,
        "captured_sources": captured_sources,
        "failed_sources": failed_sources,
        "created_at": raw["_captured_at"],
        "year": year,
        "raw_bytes": len(raw_json.encode("utf-8")),
        "compressed_bytes": len(payload_b64.encode("ascii")),
    }
    snapshot_data = {
        "_format": _FORMAT_V1,
        "_payload": payload_b64,
        "_hash": sha,
        "_locked": locked,
        "_meta": meta,
    }
    return snapshot_data, {"year": year, "hash": sha, "locked": locked, "meta": meta}


async def _build_v2_snapshot_data(
    db: AsyncSession, project_id: UUID, year: int, reason: str, lock: bool | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """v2 manifest：11 类分片 hash + 根 hash + operation/version refs。"""
    captured_at = datetime.now(timezone.utc).isoformat()
    shards: dict[str, Any] = {}
    shard_hashes: dict[str, str] = {}
    captured_sources: list[str] = []
    failed_sources: list[str] = []

    for key in _SHARD_ORDER:
        capturer = _SHARD_CAPTURERS[key]
        try:
            value = await capturer(db, project_id, year)
            captured_sources.append(key)
        except Exception as e:  # noqa: BLE001 — 单分片失败记 partial，不阻断
            logger.warning(
                "ConsolSnapshot v2 分片 %s 采集失败（项目=%s 年度=%s）：%s",
                key, project_id, year, e,
            )
            value = None
            failed_sources.append(key)
        shards[key] = value
        shard_hashes[key] = _shard_hash(value)

    operation = await _latest_succeeded_operation(db, project_id, year)
    operation_ref = _manifest_operation_ref(shards.get("lifecycle"))
    version_ref = _manifest_version_ref(operation)
    partial = bool(failed_sources)

    manifest = _build_v2_manifest(
        shards,
        shard_hashes,
        captured_sources=captured_sources,
        failed_sources=failed_sources,
        operation_ref=operation_ref,
        version_ref=version_ref,
        partial=partial,
    )
    root = manifest["root_hash"]

    # payload 存全部分片原始数据（canonical），供还原时逐分片重算 hash 与根 hash。
    raw = {
        "project_id": str(project_id),
        "year": year,
        "_captured_at": captured_at,
        "shards": shards,
    }
    raw_json = _canonical_json(raw)
    payload_b64 = _compress_payload(raw_json)
    locked = lock if lock is not None else (reason.lower() in _LOCK_REASONS)

    meta = {
        "counts": manifest["counts"],
        "captured_sources": captured_sources,
        "failed_sources": failed_sources,
        "partial": partial,
        "created_at": captured_at,
        "year": year,
        "raw_bytes": len(raw_json.encode("utf-8")),
        "compressed_bytes": len(payload_b64.encode("ascii")),
    }
    snapshot_data = {
        "_format": _FORMAT_V2,
        "_payload": payload_b64,
        "_hash": root,          # 根 hash 复用 _hash，归档 provider 据此校验完整性
        "_locked": locked,
        "_meta": meta,
        "_manifest": manifest,  # 分片 hash + 根 hash + operation/version refs
    }
    return snapshot_data, {
        "year": year,
        "hash": root,
        "locked": locked,
        "meta": meta,
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# 还原快照 + 哈希校验（5E.3 / S8）
# ---------------------------------------------------------------------------

def restore_consol_snapshot(snapshot: Any) -> dict:
    """从 ConsolSnapshot 反序列化还原"签字时合并数" + SHA-256 完整性校验（S8）。

    Args:
        snapshot: ConsolSnapshot ORM 实例（或含 snapshot_data 属性的对象）

    Returns:
        {"data": <raw_dict>, "hash_valid": bool, "hash": <stored_hash>, "locked": bool}

    兼容旧空壳快照（无 _format/_payload）：返回 data=原始 snapshot_data + hash_valid=False。
    """
    snapshot_data = getattr(snapshot, "snapshot_data", None) or {}

    fmt = snapshot_data.get("_format")

    # v2 manifest：逐分片 hash + 根 hash 全部校验（R9.3 恢复须校验全部 hash）。
    if fmt == _FORMAT_V2 and "_payload" in snapshot_data:
        return _restore_v2(snapshot_data)

    # 旧空壳快照（{created_at} 或无压缩 payload）：原样返回，标记 hash 不可校验
    if fmt != _FORMAT_V1 or "_payload" not in snapshot_data:
        return {
            "data": snapshot_data,
            "hash_valid": False,
            "hash": snapshot_data.get("_hash"),
            "locked": bool(snapshot_data.get("_locked", False)),
            "legacy": True,
        }

    # v1 gzip+base64：整体一个 hash。
    stored_hash = snapshot_data.get("_hash")
    try:
        raw_json = _decompress_payload(snapshot_data["_payload"])
        raw = json.loads(raw_json)
        recomputed = _sha256_hex(raw_json)
        hash_valid = (recomputed == stored_hash)
    except Exception as e:  # noqa: BLE001
        logger.warning("ConsolSnapshot 还原失败：%s", e)
        return {
            "data": {},
            "hash_valid": False,
            "hash": stored_hash,
            "locked": bool(snapshot_data.get("_locked", False)),
            "error": str(e)[:200],
        }

    return {
        "data": raw,
        "hash_valid": hash_valid,
        "hash": stored_hash,
        "locked": bool(snapshot_data.get("_locked", False)),
        "meta": snapshot_data.get("_meta"),
    }


def _restore_v2(snapshot_data: dict[str, Any]) -> dict:
    """还原 v2 manifest：解压分片数据，逐分片重算 hash 与根 hash，全部匹配才 hash_valid。

    返回 ``data`` 兼顾两种消费口径：顶层既含 ``shards`` 原始结构，也把各分片
    展平到顶层（便于 ``compare_snapshot_to_current`` 等按分片名直接取）。
    """
    stored_root = snapshot_data.get("_hash")
    manifest = snapshot_data.get("_manifest") or {}
    stored_shard_hashes: dict[str, str] = dict(manifest.get("shard_hashes") or {})
    try:
        raw_json = _decompress_payload(snapshot_data["_payload"])
        raw = json.loads(raw_json)
    except Exception as e:  # noqa: BLE001
        logger.warning("ConsolSnapshot v2 还原失败：%s", e)
        return {
            "data": {},
            "hash_valid": False,
            "hash": stored_root,
            "locked": bool(snapshot_data.get("_locked", False)),
            "error": str(e)[:200],
        }

    shards = raw.get("shards") or {}
    recomputed_hashes: dict[str, str] = {}
    shard_mismatches: list[str] = []
    for key in _SHARD_ORDER:
        if key not in stored_shard_hashes and key not in shards:
            continue
        recomputed = _shard_hash(shards.get(key))
        recomputed_hashes[key] = recomputed
        if recomputed != stored_shard_hashes.get(key):
            shard_mismatches.append(key)

    recomputed_root = _root_hash(recomputed_hashes)
    root_valid = (recomputed_root == stored_root)
    manifest_root_valid = (manifest.get("root_hash") == stored_root)
    hash_valid = root_valid and manifest_root_valid and not shard_mismatches

    # 展平分片到顶层，兼容按分片名直接取（trial/report/consol_notes...）。
    data: dict[str, Any] = {
        "project_id": raw.get("project_id"),
        "year": raw.get("year"),
        "shards": shards,
    }
    for key, value in shards.items():
        data.setdefault(key, value)

    return {
        "data": data,
        "hash_valid": hash_valid,
        "hash": stored_root,
        "root_valid": root_valid,
        "shard_mismatches": shard_mismatches,
        "locked": bool(snapshot_data.get("_locked", False)),
        "manifest": manifest,
        "meta": snapshot_data.get("_meta"),
    }


# ---------------------------------------------------------------------------
# 签字时 vs 当前对比（5E.3）
# ---------------------------------------------------------------------------

async def compare_snapshot_to_current(db: AsyncSession, snapshot: Any) -> dict:
    """对比快照中"签字时合并数" vs 当前实时 consol_trial 的 consol_amount（5E.3）。

    供签字合伙人核查：签字后子公司数据/抵销若被改，逐科目展示差异。

    Returns:
        {
          "by_account": [{account_code, snapshot_amount, current_amount, changed}],
          "changed_count": int,
          "hash_valid": bool,
        }
    """
    restored = restore_consol_snapshot(snapshot)
    snapshot_trial = restored["data"].get("trial", []) if restored.get("data") else []
    snap_map: dict[str, Decimal] = {}
    for row in snapshot_trial:
        code = row.get("standard_account_code")
        if code is not None:
            snap_map[code] = Decimal(str(row.get("consol_amount", "0")))

    # 查当前 consol_trial
    project_id = getattr(snapshot, "project_id", None)
    year = getattr(snapshot, "year", None)
    current_map: dict[str, Decimal] = {}
    if project_id is not None and year is not None:
        try:
            current_rows = await _capture_trial(db, project_id, year)
            for row in current_rows:
                code = row.get("standard_account_code")
                if code is not None:
                    current_map[code] = Decimal(str(row.get("consol_amount", "0")))
        except Exception as e:  # noqa: BLE001
            logger.warning("compare_snapshot_to_current 取当前数据失败：%s", e)

    by_account: list[dict] = []
    changed_count = 0
    for code in sorted(set(snap_map) | set(current_map)):
        snap_amt = snap_map.get(code, Decimal("0"))
        cur_amt = current_map.get(code, Decimal("0"))
        changed = snap_amt != cur_amt
        if changed:
            changed_count += 1
        by_account.append({
            "account_code": code,
            "snapshot_amount": str(snap_amt),
            "current_amount": str(cur_amt),
            "changed": changed,
        })

    return {
        "by_account": by_account,
        "changed_count": changed_count,
        "hash_valid": restored.get("hash_valid", False),
    }
