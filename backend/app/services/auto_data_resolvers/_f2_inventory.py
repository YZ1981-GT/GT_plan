"""F2 存货底稿 Auto Data Resolvers — 科目1401~1412 / 明细聚合 / 库龄分布."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)

_F2_INVENTORY_ACCOUNTS = tuple(f"140{i}" for i in range(1, 13))

_F2_DETAIL_SHEETS = tuple(f"F2-{i}" for i in range(3, 14))

_SHEET_LABELS: dict[str, str] = {
    "F2-3": "原材料",
    "F2-4": "材料采购在途",
    "F2-5": "周转材料",
    "F2-6": "自制半成品",
    "F2-7": "委托加工物资",
    "F2-8": "库存商品",
    "F2-9": "发出商品",
    "F2-10": "开发产品",
    "F2-11": "开发成本",
    "F2-12": "合同履约成本",
    "F2-13": "消耗性生物资产",
}


def _parse_rows(remark: str | None) -> list[dict[str, Any]]:
    if not remark:
        return []
    try:
        parsed = json.loads(remark)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _num(v: Any) -> float:
    try:
        n = float(v)
        return n if n == n else 0.0
    except (TypeError, ValueError):
        return 0.0


@auto_resolver("f2_tb_inventory")
async def _resolve_f2_tb_inventory(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 汇总存货科目组 1401~1412 期初/期末未审数."""
    placeholders = ", ".join(f":a{i}" for i in range(len(_F2_INVENTORY_ACCOUNTS)))
    params: dict[str, Any] = {
        "pid": str(project_id),
        "year": year,
        **{f"a{i}": code for i, code in enumerate(_F2_INVENTORY_ACCOUNTS)},
    }

    async def _sum(year_val: int) -> float:
        r = await db.execute(
            sa.text(f"""
                SELECT COALESCE(SUM(unadjusted_amount), 0) AS total
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code IN ({placeholders})
            """),
            {**params, "year": year_val},
        )
        row = r.fetchone()
        return float(row.total) if row else 0.0

    current = await _sum(year)
    prior = await _sum(year - 1)
    summary = f"存货1401~1412: 期末未审={current:,.0f}，期初未审={prior:,.0f}"
    return {
        "summary": summary,
        "current_unadjusted": current,
        "prior_unadjusted": prior,
        "account_codes": list(_F2_INVENTORY_ACCOUNTS),
    }


@auto_resolver("f2_detail_aggregation")
async def _resolve_f2_detail_aggregation(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 F2-3~13 明细 remark JSON 聚合期末/期初合计."""
    item_ids = [f"{s}-rows" for s in _F2_DETAIL_SHEETS]
    placeholders = ", ".join(f":id{i}" for i in range(len(item_ids)))
    params: dict[str, Any] = {"pid": str(project_id), **{f"id{i}": iid for i, iid in enumerate(item_ids)}}

    r = await db.execute(
        sa.text(f"""
            SELECT cr.item_id, cr.remark
            FROM checklist_responses cr
            WHERE cr.project_id = :pid
              AND cr.item_id IN ({placeholders})
        """),
        params,
    )

    categories: list[dict[str, Any]] = []
    closing_total = 0.0
    opening_total = 0.0

    rows_by_item = {row.item_id: row.remark for row in r.fetchall()}

    for sheet in _F2_DETAIL_SHEETS:
        item_id = f"{sheet}-rows"
        detail_rows = _parse_rows(rows_by_item.get(item_id))
        opening = sum(_num(row.get("openingAmt")) for row in detail_rows)
        closing = sum(_num(row.get("closingAmt")) for row in detail_rows)
        if opening or closing:
            categories.append({
                "sheet": sheet,
                "label": _SHEET_LABELS.get(sheet, sheet),
                "opening_amt": opening,
                "closing_amt": closing,
                "row_count": len(detail_rows),
            })
        opening_total += opening
        closing_total += closing

    summary = f"F2明细聚合: {len(categories)}类有数，期末合计={closing_total:,.0f}"
    return {
        "summary": summary,
        "closing_total": closing_total,
        "opening_total": opening_total,
        "categories": categories,
    }


@auto_resolver("f2_aging_distribution")
async def _resolve_f2_aging_distribution(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """统计 F2-3~13 明细库龄四段分布."""
    item_ids = [f"{s}-rows" for s in _F2_DETAIL_SHEETS]
    placeholders = ", ".join(f":id{i}" for i in range(len(item_ids)))
    params: dict[str, Any] = {"pid": str(project_id), **{f"id{i}": iid for i, iid in enumerate(item_ids)}}

    r = await db.execute(
        sa.text(f"""
            SELECT cr.remark FROM checklist_responses cr
            WHERE cr.project_id = :pid AND cr.item_id IN ({placeholders})
        """),
        params,
    )

    lt1 = y1to2 = y2to3 = gt3 = 0.0
    for row in r.fetchall():
        for detail in _parse_rows(row.remark):
            lt1 += _num(detail.get("agingLt1"))
            y1to2 += _num(detail.get("aging1to2"))
            y2to3 += _num(detail.get("aging2to3"))
            gt3 += _num(detail.get("agingGt3"))

    total = lt1 + y1to2 + y2to3 + gt3
    summary = (
        f"库龄分布: 1年内={lt1:,.0f} 1-2年={y1to2:,.0f} "
        f"2-3年={y2to3:,.0f} 3年以上={gt3:,.0f} 合计={total:,.0f}"
    )
    return {
        "summary": summary,
        "lt1": lt1,
        "y1to2": y1to2,
        "y2to3": y2to3,
        "gt3": gt3,
        "total": total,
    }
