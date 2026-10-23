"""D-1：合并抵销分录汇总表 — 按分录类型分类汇总。

GET /api/consolidation/worksheet/entry-summary

返回已审批分录按 entry_type 分组的借方合计、贷方合计、净额、笔数；
以及全部分录的总借方、总贷方、总净额（应为 0 = 借贷平衡）。

不读 CalcBasis（轻量只读查询），直接从 elimination_entries 汇总。
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import EliminationEntry
from app.services.project_audit_year import resolve_project_audit_year

_TYPE_LABELS: dict[str, str] = {
    "equity": "权益抵销",
    "internal_trade": "内部交易抵销",
    "internal_ar_ap": "内部往来抵销",
    "unrealized_profit": "未实现利润抵销",
    "other_adjustment": "其他调整",
}


async def entry_summary(db: AsyncSession, project_id: UUID, year: int | None) -> dict:
    """按分录类型汇总已审批的抵销分录。"""
    if year is None:
        from app.models.core import Project
        proj = await db.get(Project, project_id)
        year = resolve_project_audit_year(proj) if proj else None
    if year is None:
        return {"types": [], "totals": {}, "year": None}

    t = EliminationEntry.__table__
    q = (
        sa.select(
            t.c.entry_type,
            sa.func.coalesce(sa.func.sum(t.c.debit_amount), 0).label("debit_total"),
            sa.func.coalesce(sa.func.sum(t.c.credit_amount), 0).label("credit_total"),
            sa.func.count().label("line_count"),
        )
        .where(
            t.c.project_id == project_id,
            t.c.year == year,
            t.c.is_deleted == sa.false(),
            t.c.review_status == "approved",
        )
        .group_by(t.c.entry_type)
        .order_by(t.c.entry_type)
    )
    rows = (await db.execute(q)).fetchall()

    types = []
    grand_debit = Decimal("0")
    grand_credit = Decimal("0")
    grand_count = 0
    for r in rows:
        debit = Decimal(str(r.debit_total))
        credit = Decimal(str(r.credit_total))
        net = debit - credit
        entry_type = str(r.entry_type.value if hasattr(r.entry_type, "value") else r.entry_type)
        types.append({
            "type": entry_type,
            "type_label": _TYPE_LABELS.get(entry_type, entry_type),
            "debit_total": str(debit),
            "credit_total": str(credit),
            "net": str(net),
            "count": int(r.line_count),
        })
        grand_debit += debit
        grand_credit += credit
        grand_count += int(r.line_count)

    return {
        "types": types,
        "totals": {
            "debit_total": str(grand_debit),
            "credit_total": str(grand_credit),
            "net": str(grand_debit - grand_credit),
            "count": grand_count,
        },
        "year": year,
    }
