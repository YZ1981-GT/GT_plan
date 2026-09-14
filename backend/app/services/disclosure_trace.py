"""附注单元格溯源 — 从 disclosure_engine.py 抽出的伴生模块

负责 trace_cell（单元格级反查 binding 元数据 + 公式展开 + 证据数据行采样）。
由 DisclosureEngine.trace_cell 委托调用，保持原有 API 签名不变。

抽出原因：disclosure_engine.py 1949 行超 800 行门禁，trace 逻辑与核心
生成/刷新完全独立，下游仅 disclosure_notes router + 测试。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.models.audit_platform_models import TrialBalance

logger = logging.getLogger(__name__)


async def trace_cell(
    db: AsyncSession,
    note_id: UUID,
    row_idx: int,
    col_idx: int,
    *,
    tb_cache: dict | None = None,
) -> dict:
    """单元格溯源：返回 binding 元数据 + 公式展开 + 命中数据行采样.

    Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.3
    Design: D5 CellTrace 溯源链 端点 schema
    Reqs:   R3.1 验收 21、22
    """
    from datetime import datetime, timezone

    # 1. 加载 note
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.id == note_id,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        return {"error": "note_not_found", "note_id": str(note_id)}

    # 2. 解析 row / col 索引
    td = note.table_data or {}
    rows = td.get("rows") or []
    if not rows and isinstance(td.get("_tables"), list) and td["_tables"]:
        first_tbl = td["_tables"][0]
        if isinstance(first_tbl, dict):
            rows = first_tbl.get("rows") or []

    if not isinstance(row_idx, int) or row_idx < 0 or row_idx >= len(rows):
        return {
            "error": "cell_index_out_of_range",
            "axis": "row",
            "row_idx": row_idx,
            "row_count": len(rows),
            "computed_value": None,
        }

    row = rows[row_idx] or {}
    values = row.get("values") or []
    if not isinstance(col_idx, int) or col_idx < 0 or col_idx >= len(values):
        return {
            "error": "cell_index_out_of_range",
            "axis": "col",
            "col_idx": col_idx,
            "col_count": len(values),
            "computed_value": None,
        }

    computed_value = values[col_idx]
    cell_meta_all = row.get("_cell_meta") or {}
    cell_meta = cell_meta_all.get(str(col_idx)) or {}
    binding_id = cell_meta.get("binding_id")
    semantic = cell_meta.get("semantic")
    computed_at = cell_meta.get("computed_at")
    if not computed_at:
        note_updated = getattr(note, "updated_at", None)
        if note_updated is not None:
            try:
                computed_at = note_updated.isoformat()
            except Exception:
                computed_at = str(note_updated)
        else:
            computed_at = datetime.now(timezone.utc).isoformat()

    if not binding_id:
        return {
            "error": "no_binding",
            "computed_value": computed_value,
            "semantic": semantic,
            "computed_at": computed_at,
        }

    # 3. 反查 binding 定义
    binding = _lookup_binding(note, row, semantic)
    if not binding:
        return {
            "error": "binding_not_found",
            "binding_id": binding_id,
            "computed_value": computed_value,
            "semantic": semantic,
            "computed_at": computed_at,
        }

    # 4. 公式展开
    formula_resolved = _expand_formula(binding)

    # 5. 抽取证据数据行
    evidence = await _gather_evidence(db, note, binding, tb_cache=tb_cache, sample_limit=100)

    return {
        "binding": dict(binding),
        "binding_id": binding_id,
        "formula_resolved": formula_resolved,
        "computed_value": computed_value,
        "evidence": evidence,
        "computed_at": computed_at,
        "semantic": semantic,
        "row_label": row.get("label"),
    }



def _lookup_binding(
    note: DisclosureNote,
    row: dict,
    semantic: str | None,
) -> dict | None:
    """从 note_template_bindings.json 反查单元格级 binding 定义."""
    if not isinstance(semantic, str) or not semantic:
        return None
    try:
        from app.services.note_template_bindings_loader import (
            get_binding_for_section,
        )
        sec_binding = get_binding_for_section(note.note_section)
    except Exception:
        return None
    if not sec_binding:
        return None
    tables = sec_binding.get("tables") or []
    if not tables or not isinstance(tables[0], dict):
        return None
    table_binding = tables[0]
    rows_def = table_binding.get("rows")
    if not isinstance(rows_def, dict):
        return None
    label = row.get("label") or ""
    row_binding = rows_def.get(label) or {}
    cells = row_binding.get("binding")
    if not isinstance(cells, dict):
        return None
    cell = cells.get(semantic)
    if not isinstance(cell, dict):
        prefix = semantic + "_col"
        for k, v in cells.items():
            if isinstance(k, str) and k.startswith(prefix) and isinstance(v, dict):
                cell = v
                break
    return cell if isinstance(cell, dict) else None


def _expand_formula(binding: dict) -> str:
    """根据 binding 元数据生成可读的公式字符串（不求值）."""
    if not isinstance(binding, dict):
        return "=UNKNOWN()"
    source = binding.get("source") or "unknown"
    codes = binding.get("account_codes") or []
    field = binding.get("field") or ""
    agg = (binding.get("agg") or "sum").lower()

    if source == "trial_balance":
        if not codes:
            return f"=TB([],'{field}')"
        parts = [f"TB('{c}','{field}')" for c in codes]
        if len(parts) == 1:
            expr = parts[0]
        else:
            expr = f"SUM({', '.join(parts)})"
        return "=" + ("-" + expr if agg == "sum_minus" else expr)

    if source == "ledger_sum":
        pf = binding.get("period_filter") or {}
        mode = pf.get("mode") or "year_range"
        start = pf.get("start", "")
        end = pf.get("end", "")
        return (
            f"=LEDGER_SUM('{field}', codes={list(codes)}, "
            f"period={{mode:{mode}, start:{start}, end:{end}}})"
        )

    if source == "aux_balance":
        aux_type = binding.get("aux_type") or ""
        return f"=AUX_BALANCE('{field}', codes={list(codes)}, aux_type='{aux_type}')"

    if source == "aux_ledger_aging":
        bucket = binding.get("bucket") or ""
        return f"=AGING('{bucket}', codes={list(codes)})"

    if source == "prior_year_note":
        section = binding.get("section") or binding.get("note_section") or ""
        return f"=PRIOR(section='{section}', field='{field or 'value'}')"

    if source == "manual":
        mv = binding.get("manual_value")
        return f"=MANUAL({mv!r})"

    if source == "formula":
        expr = binding.get("expression") or binding.get("formula") or ""
        return f"=FORMULA({expr!r})"

    return f"=UNKNOWN(source={source!r})"


async def _gather_evidence(
    db: AsyncSession,
    note: DisclosureNote,
    binding: dict,
    *,
    tb_cache: dict | None = None,
    sample_limit: int = 100,
) -> dict:
    """采样命中证据数据 — 三类来源各 ≤ sample_limit 行."""
    codes = [c for c in (binding.get("account_codes") or []) if isinstance(c, str)]
    source = binding.get("source") or ""
    evidence: dict[str, list] = {
        "trial_balance_rows": [],
        "ledger_sample": [],
        "aux_balance_sample": [],
    }

    # ---- trial_balance_rows ----
    _tb_cache = tb_cache or {}
    if codes and _tb_cache:
        picked = []
        for c in codes:
            entry = _tb_cache.get(c)
            if isinstance(entry, dict):
                picked.append({"account_code": c, **entry})
            if len(picked) >= sample_limit:
                break
        evidence["trial_balance_rows"] = picked[:sample_limit]
    elif codes and source == "trial_balance":
        try:
            result = await db.execute(
                sa.select(
                    TrialBalance.standard_account_code,
                    TrialBalance.audited_amount,
                    TrialBalance.opening_balance,
                )
                .where(
                    TrialBalance.project_id == note.project_id,
                    TrialBalance.year == note.year,
                    TrialBalance.standard_account_code.in_(codes),
                    TrialBalance.is_deleted == sa.false(),
                )
                .limit(sample_limit)
            )
            for row in result.all():
                evidence["trial_balance_rows"].append({
                    "account_code": row.standard_account_code,
                    "audited": float(row.audited_amount or 0),
                    "opening": float(row.opening_balance or 0),
                })
        except Exception as err:
            logger.debug("trace_cell tb sample failed: %s", err)

    # ---- ledger_sample ----
    if codes and source == "ledger_sum":
        try:
            from app.models.audit_platform_models import TbLedger
            stmt = (
                sa.select(
                    TbLedger.account_code,
                    TbLedger.voucher_date,
                    TbLedger.debit_amount,
                    TbLedger.credit_amount,
                    TbLedger.summary,
                )
                .where(
                    TbLedger.project_id == note.project_id,
                    TbLedger.year == note.year,
                    TbLedger.is_deleted == sa.false(),
                    TbLedger.account_code.in_(codes),
                )
                .limit(sample_limit)
            )
            result = await db.execute(stmt)
            for r in result.all():
                evidence["ledger_sample"].append({
                    "account_code": r.account_code,
                    "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
                    "debit": float(r.debit_amount or 0),
                    "credit": float(r.credit_amount or 0),
                    "summary": r.summary or "",
                })
        except Exception as err:
            logger.debug("trace_cell ledger sample failed: %s", err)

    # ---- aux_balance_sample ----
    if codes and source in ("aux_balance", "aux_ledger_aging"):
        try:
            from app.models.audit_platform_models import TbAuxBalance
            where = [
                TbAuxBalance.project_id == note.project_id,
                TbAuxBalance.year == note.year,
                TbAuxBalance.is_deleted == sa.false(),
                TbAuxBalance.account_code.in_(codes),
            ]
            aux_type = binding.get("aux_type")
            if isinstance(aux_type, str) and aux_type:
                where.append(TbAuxBalance.aux_type == aux_type)
            stmt = (
                sa.select(
                    TbAuxBalance.account_code,
                    TbAuxBalance.aux_type,
                    TbAuxBalance.aux_name,
                    TbAuxBalance.closing_balance,
                    TbAuxBalance.opening_balance,
                )
                .where(*where)
                .limit(sample_limit)
            )
            result = await db.execute(stmt)
            for r in result.all():
                evidence["aux_balance_sample"].append({
                    "account_code": r.account_code,
                    "aux_type": r.aux_type,
                    "aux_name": r.aux_name,
                    "closing": float(r.closing_balance or 0),
                    "opening": float(r.opening_balance or 0),
                })
        except Exception as err:
            logger.debug("trace_cell aux_balance sample failed: %s", err)

    return evidence
