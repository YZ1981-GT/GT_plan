"""试算平衡表的单元格来源（spec citar-cell-source-hover R4，design §5）。

与 ``build_standard_balance_view`` 同源：末级行（``leaf_balance_rows``）与已批准调整（``approved_adjustment_lines``）
就是 standard-view 求和的那两组行，所以各列构成之和 = 格值（期初、审定数取 trial_balance，对不上时如实给差额）。

cell_key：``{标准科目}:{列}``；列：opening / period_debit / period_credit / adj_debit / adj_credit / adj_closing /
src_debit / src_credit / audited（后两组是「底稿取数余额表」页签）。金额借正贷负。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment, AdjustmentEntry, TrialBalance
from app.services.cell_source.schema import item, link, source
from app.services.ledger_import.direction_resolver import resolve_account_direction
from app.services.standard_balance_view_service import (
    approved_adjustment_lines,
    build_standard_balance_view,
    is_pl_standard_code,
    leaf_balance_rows,
)

_ZERO = Decimal(0)
_STALE = "与科目余额表、调整分录现算不一致，试算表需重算（点「重算」）"
_PENDING = ("draft", "pending_review", "rejected")


def _d(v) -> Decimal:
    return Decimal(str(v)) if v is not None else _ZERO


async def _pending_lines(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """未批准（草稿 / 待复核 / 驳回）、非底稿来源的调整分录行：只列出、不计入。"""
    adj, ae = Adjustment.__table__, AdjustmentEntry.__table__
    q = (
        sa.select(adj.c.entry_group_id, adj.c.adjustment_no, adj.c.review_status, ae.c.standard_account_code,
                  ae.c.debit_amount, ae.c.credit_amount)
        .select_from(ae.join(adj, ae.c.adjustment_id == adj.c.id))
        .where(adj.c.project_id == project_id, adj.c.year == year, adj.c.is_deleted == sa.false(),
               sa.cast(adj.c.review_status, sa.String).in_(_PENDING),
               sa.or_(adj.c.origin.is_(None), adj.c.origin != "workpaper"))
    )
    return [{"group": str(r[0]), "no": r[1], "status": str(getattr(r[2], "value", r[2])), "code": r[3],
             "debit": _d(r[4]), "credit": _d(r[5])} for r in (await db.execute(q)).fetchall() if r[3]]


_STATUS_LABEL = {"draft": "草稿", "pending_review": "待复核", "rejected": "已驳回"}


def _adj_items(lines: list[dict], side: str, sign: int = 1, pending: bool = False) -> list[dict]:
    """按分录组合计一侧（借 / 贷）；同组多行合并。"""
    groups: dict[str, dict] = {}
    for line in lines:
        amount = line[side]
        if not amount:
            continue
        g = groups.setdefault(line["group"], {"no": line["no"], "desc": line.get("description"),
                                              "status": line.get("status"), "amount": _ZERO})
        g["amount"] += amount
    out = []
    for gid, g in groups.items():
        detail = f"{_STATUS_LABEL.get(g['status'], g['status'])}，批准后才计入" if pending else (g["desc"] or None)
        out.append(item(f"调整分录 {g['no']}", g["amount"], sign=0 if pending else sign, detail=detail,
                        link_to=link("adjustments", group=gid)))
    return out


def _leaf_items(leaves: list[dict], field: str) -> list[dict]:
    return [item(f"{r['code']} {r['name'] or ''}".strip(), r[field], link_to=link("balance", code=r["code"]))
            for r in leaves if r[field]]


async def trial_balance_sources(
    db: AsyncSession, project_id: UUID, year: int, company_code: str = "001", scope_codes: set[str] | None = None,
) -> dict:
    """``{year, cells: {"{标准科目}:{列}": CellSource}, notices}``；``scope_codes`` 为受限成员可见科目（None = 不限）。"""
    # 先跑经 get_active_filter 的查询（失败时会 rollback，ORM 对象过期），trial_balance 最后读、立即取成普通值
    view = await build_standard_balance_view(db, project_id, year, company_code)
    leaves = await leaf_balance_rows(db, project_id, year)
    approved = await approved_adjustment_lines(db, project_id, year)
    pending = await _pending_lines(db, project_id, year)
    tb = {
        r.standard_account_code: {"unadj": r.unadjusted_amount, "aje": r.aje_adjustment, "rje": r.rje_adjustment,
                                  "wp": r.wp_adjustment, "name": r.account_name}
        for r in (await db.execute(sa.select(TrialBalance).where(
            TrialBalance.project_id == project_id, TrialBalance.year == year,
            TrialBalance.company_code == company_code, TrialBalance.is_deleted == sa.false(),
        ))).scalars().all()
    }

    def by_code(rows: list[dict], key: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r[key], []).append(r)
        return out

    leaf_by, appr_by, pend_by = by_code(leaves, "std"), by_code(approved, "code"), by_code(pending, "code")
    cells: dict[str, dict] = {}
    for r in view:
        code = r["standard_account_code"]
        if scope_codes is not None and code not in scope_codes:
            continue
        leaf, appr, pend = leaf_by.get(code, []), appr_by.get(code, []), pend_by.get(code, [])
        to_signed = Decimal(-1) if r["direction"] == "credit" else Decimal(1)
        opening, pd, pc = _d(r["opening_balance"]), _d(r["period_debit"]), _d(r["period_credit"])
        ad, ac, wp = _d(r["adjustment_debit"]), _d(r["adjustment_credit"]), _d(r["wp_adjustment"])
        closing, adj_closing = _d(r["closing_balance"]), _d(r["adjusted_closing_balance"])
        pl_note = ["损益类科目：期末为结转后的余额（每期结转损益的账套年末通常为 0）"] if is_pl_standard_code(code) else []

        s = source("import", "期初余额：试算表期初数（科目余额表末级科目期初，经映射汇总）", opening,
                   _leaf_items(leaf, "opening"), linear=bool(leaf))
        if s["diff"]:
            s["issue"] = _STALE
        cells[f"{code}:opening"] = s
        cells[f"{code}:period_debit"] = source("import", "本期借方发生额：科目余额表末级科目，经映射汇总", pd,
                                               _leaf_items(leaf, "debit"), linear=True)
        cells[f"{code}:period_credit"] = source("import", "本期贷方发生额：科目余额表末级科目，经映射汇总", pc,
                                                _leaf_items(leaf, "credit"), linear=True)
        adj_note = ["只计已批准的调整分录；底稿来源的调整已由审定表发布，计入「底稿发布调整」"]
        cells[f"{code}:adj_debit"] = source("adjustment", "借方审计调整", ad,
                                            _adj_items(appr, "debit") + _adj_items(pend, "debit", pending=True),
                                            linear=True, notes=adj_note)
        cells[f"{code}:adj_credit"] = source("adjustment", "贷方审计调整", ac,
                                             _adj_items(appr, "credit") + _adj_items(pend, "credit", pending=True),
                                             linear=True, notes=adj_note)
        first_leaf = link("balance", code=leaf[0]["code"]) if leaf else None
        closing_items = [item("未审期末（科目余额表末级合计）", closing, link_to=first_leaf),
                         item("借方审计调整", ad), item("贷方审计调整", ac, sign=-1)]
        if wp:
            closing_items.append(item("底稿发布调整", wp))
        cells[f"{code}:adj_closing"] = source("derived", "调整后期末 = 未审期末 + 借方调整 − 贷方调整 + 底稿发布调整",
                                              adj_closing, closing_items, linear=True, notes=pl_note)
        cells[f"{code}:src_debit"] = source("derived", "本期借方（含审计调整）", pd + ad,
                                            [item("本期借方发生额", pd), item("借方审计调整", ad)], linear=True)
        cells[f"{code}:src_credit"] = source("derived", "本期贷方（含审计调整）", pc + ac,
                                             [item("本期贷方发生额", pc), item("贷方审计调整", ac)], linear=True)

        t = tb.get(code)
        if r["audited_amount"] is None or t is None:
            cells[f"{code}:audited"] = source("derived", "试算表没有审定数，显示调整后期末", adj_closing, closing_items,
                                              linear=True, notes=pl_note)
            continue
        audited = _d(r["audited_amount"]) * to_signed
        parts = [item("未审数", _d(t["unadj"]) * to_signed), item("审计调整（AJE）", _d(t["aje"]) * to_signed),
                 item("重分类调整（RJE）", _d(t["rje"]) * to_signed)]
        if t["wp"]:
            parts.append(item("底稿发布调整", _d(t["wp"]) * to_signed))
        s = source("derived", "审定数 = 未审数 + 审计调整 + 重分类调整 + 底稿发布调整（试算表；平台审计底稿取数读这一列）",
                   audited, parts, linear=True,
                   notes=pl_note + ["调整明细见「审定科目余额表」借方 / 贷方审计调整列"])
        if s["diff"] or (not is_pl_standard_code(code) and abs(audited - adj_closing) >= Decimal("0.005")):
            s["issue"] = _STALE
        cells[f"{code}:audited"] = s
    return {"year": year, "cells": cells, "notices": []}
