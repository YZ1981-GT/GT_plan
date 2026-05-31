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


# 数据源采集器注册表：(键, 采集函数)
_CAPTURERS: tuple[tuple[str, Any], ...] = (
    ("trial", _capture_trial),
    ("worksheet", _capture_worksheet),
    ("report", _capture_report),
    ("notes", _capture_notes),
)


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
) -> dict:
    """序列化签字时刻全量合并数据 → 哈希 → 压缩 → 存 ConsolSnapshot（5E.2）。

    Args:
        db: 异步会话
        project_id: 合并母项目 ID
        year: 年度
        reason: 触发原因（sign/signed/lock 等会令快照锁定只读）
        user_id: 操作人（审计留痕用）
        lock: 显式锁定标志；None 时按 reason 推断（签字类原因→锁定）

    Returns:
        {"id", "year", "hash", "locked", "meta"}

    单源采集失败不影响整体：记录 captured_sources，仍创建快照（5E.2 健壮性）。
    审计留痕失败不破坏快照创建（5E.4，try/except + warning）。
    """
    from app.models.phase10_models import ConsolSnapshot

    captured_sources: list[str] = []
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
        except Exception as e:  # noqa: BLE001 — 单源失败不阻断快照创建
            logger.warning(
                "ConsolSnapshot 采集数据源 %s 失败（项目=%s 年度=%s）：%s",
                key, project_id, year, e,
            )
            raw[key] = []
            counts[key] = 0

    # 序列化 → 哈希（压缩前的原始 JSON）→ 压缩
    raw_json = _canonical_json(raw)
    sha = _sha256_hex(raw_json)
    payload_b64 = _compress_payload(raw_json)

    locked = lock if lock is not None else (reason.lower() in _LOCK_REASONS)

    meta = {
        "counts": counts,
        "captured_sources": captured_sources,
        "created_at": raw["_captured_at"],
        "year": year,
        "raw_bytes": len(raw_json.encode("utf-8")),
        "compressed_bytes": len(payload_b64.encode("ascii")),
    }

    snapshot_data = {
        "_format": "gzip+base64",
        "_payload": payload_b64,
        "_hash": sha,
        "_locked": locked,
        "_meta": meta,
    }

    snap = ConsolSnapshot(
        project_id=project_id,
        year=year,
        snapshot_data=snapshot_data,
        trigger_reason=reason[:30],
        created_by=user_id,
    )
    db.add(snap)
    await db.flush()  # 取 snap.id；commit 由路由层负责（与审计留痕同事务）

    # 5E.4 审计留痕（复用 Phase 0 log_consol_action）；失败不破坏快照创建
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
                after={"hash": sha, "locked": locked, "reason": reason, "counts": counts},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ConsolSnapshot 审计留痕失败（快照 %s 仍创建）：%s", snap.id, e)

    await db.commit()

    return {
        "id": str(snap.id),
        "year": year,
        "hash": sha,
        "locked": locked,
        "meta": meta,
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

    # 旧空壳快照（{created_at} 或无压缩 payload）：原样返回，标记 hash 不可校验
    if snapshot_data.get("_format") != "gzip+base64" or "_payload" not in snapshot_data:
        return {
            "data": snapshot_data,
            "hash_valid": False,
            "hash": snapshot_data.get("_hash"),
            "locked": bool(snapshot_data.get("_locked", False)),
            "legacy": True,
        }

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
