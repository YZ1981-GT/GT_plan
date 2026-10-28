"""合并抵销分录汇总表（spec consol-autotree-linkage-closure R9，design §3.7）。

GET /api/consolidation/worksheet/entry-summary

与合并试算 / 合并报表同一计算口径（``consol_calc_basis``）：只计**已审批且归属成功**的分录，
按 差额节点（树序）× 科目 × 分录类型 列原始借方 / 贷方、按科目自然方向归一的净额（``sign × (借 − 贷)``）
与分录笔数；「含草稿」净额取同一树与试算表上的预览口径（已审批 + 草稿 + 待审批，不含已驳回）。

🔴 旧实现是另一条 SQL：只按类型分组、只看本项目、不认归属、类型标签键 ``other_adjustment`` 与枚举 ``other``
对不上 ⇒ 与合并试算两套数。现在：

- ``reconcile``：逐科目 Σ 调整 / Σ 抵销 与 ``trial_amounts``（合并试算同一函数）对账；
  ``persisted_stale`` = 已落库的合并试算与读时结果不一致（或标了待更新）⇒ 提示重新推送；
- ``orphans``：找不到归属差额节点的分录单列原因，不计入；
- ``warnings``：内部往来 / 内部交易抵销分录让相关科目余额同时增加（所有明细行归一净额 > 0）⇒ 方向可能录反。
只读，不写库。
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0")
_TOLERANCE = Decimal("0.005")
#: 展示顺序：权益 → 往来 → 交易 → 未实现利润 → 其他调整（与分录枚举一致）
TYPE_ORDER: tuple[str, ...] = ("equity", "internal_ar_ap", "internal_trade", "unrealized_profit", "other")
#: 方向提示只看这两类：抵销后相关科目余额应同时减少
DIRECTION_CHECKED_TYPES = frozenset({"internal_ar_ap", "internal_trade"})


def _type_rank(entry_type: str) -> tuple[int, str]:
    return (TYPE_ORDER.index(entry_type) if entry_type in TYPE_ORDER else len(TYPE_ORDER), entry_type)


def _s(value: Decimal) -> str:
    """到分的金额字符串；负零（``-1 × 0``）归正，不显示「-0.00」。"""
    from app.services.consol_calc_basis import to_cents

    cents = to_cents(value)
    return str(abs(cents) if cents == 0 else cents)


def _empty(year: int | None, warning: str) -> dict:
    return {
        "year": year, "rows": [], "by_type": [],
        "totals": {"debit": "0.00", "credit": "0.00", "difference": "0.00", "balanced": True, "entry_count": 0},
        "reconcile": {"matched": True, "mismatches": [], "persisted_stale": False, "stale_accounts": []},
        "orphans": [], "warnings": [warning],
    }


def _type_cells(basis: Any, node_key: str) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """差额节点 → {(科目, 类型): (原始借, 原始贷)}。"""
    out: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for account, totals in basis.elim_totals.get(node_key, {}).items():
        for entry_type, (debit, credit) in totals.by_type.items():
            out[(account, entry_type)] = (debit, credit)
    return out


def _entry_counts(basis: Any, records: Iterable[Any]) -> dict[tuple[str, str, str], set[UUID]]:
    """(差额节点, 科目, 类型) → 计入的分录 id 集合（只看已归属的记录）。"""
    out: dict[tuple[str, str, str], set[UUID]] = {}
    for rec in records:
        key = basis.attributed.get(rec.id)
        if key is None:
            continue
        for line in rec.lines:
            out.setdefault((key, line.account_code, rec.entry_type), set()).add(rec.id)
    return out


def summary_rows(basis: Any, draft_basis: Any, records: Iterable[Any], project_id: UUID) -> list[dict]:
    """差额节点（树序）× 科目 × 类型的明细行；预览口径独有的（只有草稿）也列出，已审批金额为 0。"""
    from app.services.consol_calc_basis import ONE
    from app.services.consol_elimination_sheet_service import ENTRY_TYPE_LABELS
    from app.services.consol_group_tree import KIND_ELIM
    from app.services.consol_report_view_service import _measure_of
    from app.services.consol_tree_service import iter_nodes

    counts = _entry_counts(basis, records)
    rows: list[dict] = []
    for node in iter_nodes(basis.tree):
        if node.kind != KIND_ELIM:
            continue
        cells = _type_cells(basis, node.node_key)
        drafts = _type_cells(draft_basis, node.node_key) if draft_basis is not None else {}
        for account, entry_type in sorted(set(cells) | set(drafts), key=lambda k: (k[0], _type_rank(k[1]))):
            sign = basis.signs.get(account, draft_basis.signs.get(account, ONE) if draft_basis else ONE)
            debit, credit = cells.get((account, entry_type), (ZERO, ZERO))
            d_debit, d_credit = drafts.get((account, entry_type), (ZERO, ZERO))
            rows.append({
                "node_key": node.node_key,
                "node_label": node.display_name or node.company_name,
                "hosted_here": node.host_project_id == project_id,
                "account_code": account,
                "account_name": basis.names.get(account) or (draft_basis.names.get(account) if draft_basis else None),
                "entry_type": entry_type,
                "type_label": ENTRY_TYPE_LABELS.get(entry_type, entry_type),
                "measure": _measure_of(entry_type),
                "debit": _s(debit),
                "credit": _s(credit),
                "net": _s(sign * (debit - credit)),
                "draft_net": _s(sign * (d_debit - d_credit)) if draft_basis is not None else None,
                "entry_count": len(counts.get((node.node_key, account, entry_type), ())),
            })
    return rows


def by_type(rows: list[dict], basis: Any, records: Iterable[Any]) -> list[dict]:
    """按类型合计（笔数按分录去重，不按明细行累加）。"""
    from app.services.consol_elimination_sheet_service import ENTRY_TYPE_LABELS

    ids: dict[str, set[UUID]] = {}
    for rec in records:
        if rec.id in basis.attributed:
            ids.setdefault(rec.entry_type, set()).add(rec.id)
    groups: dict[str, list[Decimal]] = {}
    for r in rows:
        acc = groups.setdefault(r["entry_type"], [ZERO, ZERO, ZERO, ZERO])
        acc[0] += Decimal(r["debit"])
        acc[1] += Decimal(r["credit"])
        acc[2] += Decimal(r["net"])
        acc[3] += Decimal(r["draft_net"] or "0")
    return [
        {"entry_type": t, "type_label": ENTRY_TYPE_LABELS.get(t, t), "debit": _s(v[0]), "credit": _s(v[1]),
         "net": _s(v[2]), "draft_net": _s(v[3]), "entry_count": len(ids.get(t, ()))}
        for t, v in sorted(groups.items(), key=lambda kv: _type_rank(kv[0]))
    ]


def reconcile_with_trial(rows: list[dict], basis: Any) -> list[dict]:
    """逐科目：本表 Σ 调整 / Σ 抵销 vs 合并试算（``trial_amounts``，同一计算口径）；返回不一致的科目。"""
    from app.services.consol_calc_basis import MEASURE_ADJUSTMENT, trial_amounts

    sums: dict[str, list[Decimal]] = {}
    for r in rows:
        acc = sums.setdefault(r["account_code"], [ZERO, ZERO])
        acc[0 if r["measure"] == MEASURE_ADJUSTMENT else 1] += Decimal(r["net"])
    trial = trial_amounts(basis)
    mismatches = []
    for code in sorted(set(sums) | {c for c, a in trial.items() if a.consol_adjustment or a.consol_elimination}):
        adj, elim = sums.get(code, [ZERO, ZERO])
        t = trial.get(code)
        t_adj = t.consol_adjustment if t else ZERO
        t_elim = t.consol_elimination if t else ZERO
        if abs(adj - t_adj) > _TOLERANCE or abs(elim - t_elim) > _TOLERANCE:
            mismatches.append({
                "account_code": code, "account_name": basis.names.get(code),
                "summary_adjustment": _s(adj), "trial_adjustment": _s(t_adj),
                "summary_elimination": _s(elim), "trial_elimination": _s(t_elim),
            })
    return mismatches


def persisted_stale_accounts(persisted: Iterable[Any], basis: Any) -> list[str]:
    """已落库合并试算与读时结果不一致（或标了待更新）的科目。"""
    from app.services.consol_calc_basis import trial_amounts

    read = {c: a for c, a in trial_amounts(basis).items() if a.consol_adjustment or a.consol_elimination}
    stale: set[str] = set()
    seen: set[str] = set()
    for row in persisted:
        code = row.standard_account_code
        seen.add(code)
        a = read.get(code)
        adj, elim = (a.consol_adjustment, a.consol_elimination) if a else (ZERO, ZERO)
        if getattr(row, "is_stale", False) or abs((row.consol_adjustment or ZERO) - adj) > _TOLERANCE \
                or abs((row.consol_elimination or ZERO) - elim) > _TOLERANCE:
            stale.add(code)
    stale |= set(read) - seen
    return sorted(stale)


def direction_warnings(records: Iterable[Any], basis: Any, statuses: dict[UUID, str]) -> list[str]:
    """内部往来 / 内部交易抵销分录：所有明细行按科目方向归一的净额都 > 0 ⇒ 相关科目余额同时增加。"""
    from app.services.consol_calc_basis import ONE, account_sign
    from app.services.consol_elimination_sheet_service import ENTRY_TYPE_LABELS, STATUS_LABELS

    out = []
    for rec in sorted(records, key=lambda r: (r.entry_no, str(r.id))):
        if rec.entry_type not in DIRECTION_CHECKED_TYPES:
            continue
        nets = [(basis.signs.get(ln.account_code) or account_sign(ln.account_code, ln.account_name) or ONE)
                * (ln.debit - ln.credit) for ln in rec.lines]
        nets = [n for n in nets if n != 0]
        if nets and all(n > 0 for n in nets):
            status = STATUS_LABELS.get(statuses.get(rec.id, ""), statuses.get(rec.id, ""))
            out.append(
                f"分录 {rec.entry_no}（{ENTRY_TYPE_LABELS.get(rec.entry_type, rec.entry_type)}，{status}）"
                "使相关科目余额同时增加，借贷方向可能录反"
            )
    return out


async def entry_summary(db: AsyncSession, project_id: UUID, year: int | None) -> dict:
    """分录汇总表（只读）：见模块说明。"""
    from app.services.consol_calc_basis import PREVIEW_STATUSES, load_tree_entries, records_from_entries
    from app.services.consol_elimination_sheet_service import STATUS_LABELS
    from app.services.consol_report_view_service import load_view_context
    from app.services.consol_trial_service import get_trial_balance

    ctx = await load_view_context(db, project_id, year, include_drafts=True)
    if ctx is None:
        return _empty(year, "不是合并项目，或无法确定审计年度")
    basis, draft = ctx.basis, ctx.draft_basis
    entries = await load_tree_entries(db, basis.tree, ctx.year, approved_only=False)
    statuses = {e.id: getattr(e.review_status, "value", e.review_status) for e in entries}
    approved, _bad = records_from_entries([e for e in entries if statuses[e.id] == "approved"])
    previewed, _bad2 = records_from_entries([e for e in entries if statuses[e.id] in PREVIEW_STATUSES])

    rows = summary_rows(basis, draft, approved, project_id)
    types = by_type(rows, basis, approved)
    debit = sum((Decimal(t["debit"]) for t in types), ZERO)
    credit = sum((Decimal(t["credit"]) for t in types), ZERO)
    mismatches = reconcile_with_trial(rows, basis)
    stale = persisted_stale_accounts(await get_trial_balance(db, project_id, ctx.year), basis)
    orphan_source = draft if draft is not None else basis
    orphans = [
        {"entry_no": o.entry_no, "reason": o.reason, "review_status": statuses.get(o.entry_id),
         "review_status_label": STATUS_LABELS.get(statuses.get(o.entry_id, ""), statuses.get(o.entry_id))}
        for o in orphan_source.orphans
    ]
    warnings: list[str] = []
    if abs(debit - credit) > _TOLERANCE:
        warnings.append(f"已审批分录借贷不平：借方 {_s(debit)}，贷方 {_s(credit)}")
    if orphans:
        warnings.append(f"{len(orphans)} 笔分录找不到归属的差额节点，未计入（见未归属分录）")
    if mismatches:
        warnings.append(f"{len(mismatches)} 个科目与合并试算的调整 / 抵销合计不一致")
    if stale:
        warnings.append(f"已落库的合并试算与当前分录不一致（{len(stale)} 个科目），请重新推送")
    warnings += direction_warnings(previewed, draft if draft is not None else basis, statuses)
    return {
        "year": ctx.year,
        "rows": rows,
        "by_type": types,
        "totals": {"debit": _s(debit), "credit": _s(credit), "difference": _s(debit - credit),
                   "balanced": abs(debit - credit) <= _TOLERANCE,
                   "entry_count": len({r.id for r in approved if r.id in basis.attributed})},
        "reconcile": {"matched": not mismatches, "mismatches": mismatches,
                      "persisted_stale": bool(stale), "stale_accounts": stale},
        "orphans": orphans,
        "warnings": warnings,
    }


__all__ = ["DIRECTION_CHECKED_TYPES", "TYPE_ORDER", "entry_summary"]
