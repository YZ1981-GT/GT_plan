"""单体财务报表（企业会计制度格式）资产负债表不平：把差额拆到源头数据行（spec citar-fs-issue-source-locate）。

D = 资产总计 − 负债和所有者权益总计。报表每行对科目余额是线性的，不计手工值时
``D_auto = Σ_c k_c·b_c + k_PL·PL_CLOSE``，k 用「只给一个科目 1 元」经 ``compute_statement`` 现算。

期末：D = 手工 + Σ(k_c − e_c)·b_c + (k_PL − 1)·PL_CLOSE + Σ_非损益(b_c − 调整后期末_c) + 调整借贷差 + 底稿发布调整合计
         − 未映射末级期末 + Σ末级期初 + Σ行内不一致 + Σ(借 − 贷)；Σ(借 − 贷) 有序时账时逐科目对到序时账。
上年年末：D = 手工 + Σ(k_c − e_c)·b_c + Σ_非损益(b_c − 映射末级期初_c) − 未映射期初 − 损益类期初 + Σ末级期初。
拆不尽的单列「其余差额未能定位」。只读，不改任何数。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TbLedger
from app.services import tax_workpaper_service as tws
from app.services.dataset_query import get_active_filter
from app.services.tax_assurance.fs_rows import (
    ASSETS_TOTAL, LIAB_EQUITY_TOTAL, PL_CLOSE, compute_statement, is_pl_code, statement_def,
)
from app.services.tb_mapping_sql import leaf_condition, resolved_standard_code, signed_balance

_ZERO = Decimal(0)
EPS = Decimal("0.005")
MAX_ROWS = 20


def _d(v: Any) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else _ZERO


def norm_code(code: Any) -> str:
    s = str(code or "").strip()
    return s[:-2] if s.endswith(".0") else s


def _money(v: Decimal) -> str:
    return f"{v:,.2f}"


@dataclass(frozen=True)
class Leaf:
    """科目余额表末级行（借正贷负）。"""
    code: str
    name: str
    std: str | None
    opening: Decimal
    debit: Decimal
    credit: Decimal
    closing: Decimal


async def load_leaves(db: AsyncSession, project_id: UUID, year: int) -> list[Leaf]:
    bal = TbBalance.__table__
    q = (
        sa.select(
            bal.c.account_code, bal.c.account_name,
            signed_balance(bal.c.opening_balance, bal.c.opening_direction).label("op"),
            bal.c.debit_amount, bal.c.credit_amount,
            signed_balance(bal.c.closing_balance, bal.c.closing_direction).label("cl"),
            resolved_standard_code(bal).label("std"),
        )
        .where(await get_active_filter(db, bal, project_id, year))
        .where(leaf_condition(bal))
    )
    return [
        Leaf(norm_code(r.account_code), r.account_name or "", r.std, _d(r.op), _d(r.debit_amount), _d(r.credit_amount), _d(r.cl))
        for r in (await db.execute(q)).fetchall()
    ]


async def load_ledger(db: AsyncSession, project_id: UUID, year: int) -> dict[str, tuple[Decimal, Decimal]]:
    """序时账按科目编码汇总 {编码: (借, 贷)}；没有序时账返回空。"""
    led = TbLedger.__table__
    q = (
        sa.select(led.c.account_code, sa.func.sum(led.c.debit_amount).label("dr"), sa.func.sum(led.c.credit_amount).label("cr"))
        .where(await get_active_filter(db, led, project_id, year))
        .group_by(led.c.account_code)
    )
    out: dict[str, tuple[Decimal, Decimal]] = {}
    for r in (await db.execute(q)).fetchall():
        code = norm_code(r.account_code)
        dr, cr = out.get(code, (_ZERO, _ZERO))
        out[code] = (dr + _d(r.dr), cr + _d(r.cr))
    return out


def _bs_diff(balances: dict[str, Decimal], pl_close: Decimal = _ZERO) -> Decimal:
    a = compute_statement(statement_def(ASSETS_TOTAL[0]), balances, pl_close)
    b = compute_statement(statement_def(LIAB_EQUITY_TOTAL[0]), balances, pl_close)
    return (a.get(ASSETS_TOTAL[1]) or _ZERO) - (b.get(LIAB_EQUITY_TOTAL[1]) or _ZERO)


@lru_cache(maxsize=4096)
def coefficient(code: str) -> Decimal:
    """该标准科目 1 元（借正贷负）使差额变动多少：应为 1（损益类为 0，经未结转损益进未分配利润）。"""
    return _bs_diff({code: Decimal(1)})


@lru_cache(maxsize=1)
def pl_close_coefficient() -> Decimal:
    return _bs_diff({}, Decimal(1))


def _row(code: str, name: str, amount: Decimal, note: str, **extra: Any) -> dict:
    return {"code": code, "name": name, "amount": amount, "note": note, **extra}


class _Sources:
    """收集差额来源：每项 = 一类原因（对差额的影响 + 源头行），最后补残差。"""

    def __init__(self) -> None:
        self.items: list[tuple[Decimal, dict]] = []
        self.total = _ZERO

    def add(self, kind: str, title: str, amount: Decimal, page: str | None, rows: list[dict] | None = None) -> None:
        if abs(amount) < EPS:
            return
        self.total += amount
        rows = sorted(rows or [], key=lambda r: -abs(r["amount"]))
        self.items.append((abs(amount), {
            "kind": kind, "title": title, "amount": tws.encode_value(amount), "page": page,
            "rows": [{**r, "amount": tws.encode_value(r["amount"])} for r in rows[:MAX_ROWS]],
            "more": max(0, len(rows) - MAX_ROWS),
        }))

    def result(self, diff: Decimal) -> list[dict]:
        out = [item for _, item in sorted(self.items, key=lambda x: -x[0])]
        rest = diff - self.total
        if abs(rest) >= EPS:
            out.append({"kind": "unexplained", "title": "其余差额未能定位到具体数据行", "amount": tws.encode_value(rest),
                        "page": None, "rows": [], "more": 0})
        return out


def _coverage(src: _Sources, balances: dict[str, Decimal], names: dict[str, str], *, include_pl: bool) -> None:
    rows, total = [], _ZERO
    for code, b in balances.items():
        pl = is_pl_code(code)
        if abs(b) < EPS or (pl and not include_pl):
            continue
        k = coefficient(code)
        expect = _ZERO if pl else Decimal(1)
        if k == expect:
            continue
        effect = (k - expect) * b
        if pl:
            note = f"损益类科目被资产负债表项目直接引用 {k.normalize()} 次（应经未结转损益进未分配利润），金额 {_money(b)}"
        elif k == 0:
            note = f"余额 {_money(b)} 没有进入资产负债表任何项目（请核对科目映射或报表行次配置）"
        else:
            note = f"在资产负债表里计入 {k.normalize()} 次（应为 1 次），余额 {_money(b)}"
        rows.append(_row(code, names.get(code, ""), effect, note))
        total += effect
    src.add("coverage", "标准科目没有（或重复）进入资产负债表项目", total, "trial_balance", rows)


def explain_current(
    *, view: list[dict], closing: dict[str, Decimal], pl_close: Decimal, leaves: list[Leaf],
    ledger: dict[str, tuple[Decimal, Decimal]] | None, d_eff: Decimal, d_auto: Decimal, manual_rows: list[dict],
) -> list[dict]:
    """期末列。``ledger`` 为 None = 没有序时账。"""
    src = _Sources()
    names = {r["standard_account_code"]: r["account_name"] for r in view}
    src.add("manual", "本页手工修改的金额", d_eff - d_auto, "statement", manual_rows)
    _coverage(src, closing, names, include_pl=True)
    k_pl = pl_close_coefficient()
    if k_pl != 1:
        src.add("coverage", "未结转损益没有按 1 次进入未分配利润（报表行次配置）", (k_pl - 1) * pl_close, "trial_balance")

    drift_rows, drift = [], _ZERO
    adj_net, wp_rows, wp_total = _ZERO, [], _ZERO
    for r in view:
        code = r["standard_account_code"]
        adjusted = _d(r["adjusted_closing_balance"])
        adj_net += _d(r["adjustment_debit"]) - _d(r["adjustment_credit"])
        wp = _d(r["wp_adjustment"])
        if abs(wp) >= EPS:
            wp_rows.append(_row(code, r["account_name"], wp, f"底稿发布调整 {_money(wp)}"))
            wp_total += wp
        if is_pl_code(code):
            continue
        delta = closing.get(code, _ZERO) - adjusted
        if abs(delta) >= EPS:
            drift_rows.append(_row(code, r["account_name"], delta,
                                   f"试算表审定数 {_money(closing.get(code, _ZERO))}，余额表 + 调整后期末 {_money(adjusted)}（请点「重算试算表」）"))
            drift += delta
    src.add("tb_stale", "试算表审定数与科目余额表 + 调整分录不一致", drift, "trial_balance", drift_rows)
    src.add("adjustment_unbalanced", "已批准的调整分录借贷合计不相等", adj_net, "adjustments")
    src.add("wp_unbalanced", "底稿发布到试算表的调整借贷不平", wp_total, "trial_balance", wp_rows)

    unmapped = [lf for lf in leaves if lf.std is None and abs(lf.closing) >= EPS]
    src.add("unmapped", "有期末余额的客户科目没有映射到标准科目，没进试算表",
            -sum((lf.closing for lf in unmapped), _ZERO), "mapping",
            [_row(lf.code, lf.name, -lf.closing, f"期末余额 {_money(lf.closing)} 未映射") for lf in unmapped])

    opening = sum((lf.opening for lf in leaves), _ZERO)
    src.add("balance_opening", "科目余额表期初余额借贷不平", opening, "balance")
    gaps = [(lf, lf.closing - lf.opening - lf.debit + lf.credit) for lf in leaves]
    gaps = [(lf, g) for lf, g in gaps if abs(g) >= EPS]
    src.add("balance_row", "科目余额表行内期初 + 借方 − 贷方 ≠ 期末", sum((g for _, g in gaps), _ZERO), "balance",
            [_row(lf.code, lf.name, g, f"期初 {_money(lf.opening)} + 借 {_money(lf.debit)} − 贷 {_money(lf.credit)} ≠ 期末 {_money(lf.closing)}")
             for lf, g in gaps])
    movement = sum((lf.debit - lf.credit for lf in leaves), _ZERO)
    if ledger:
        _ledger_sources(src, leaves, ledger)
    else:
        debit = sum((lf.debit for lf in leaves), _ZERO)
        credit = sum((lf.credit for lf in leaves), _ZERO)
        src.add("balance_movement", f"科目余额表本期借方合计 {_money(debit)}、贷方合计 {_money(credit)}，不相等（没有序时账，无法逐科目核对）",
                movement, "balance")
    return src.result(d_eff)


def _ledger_sources(src: _Sources, leaves: list[Leaf], ledger: dict[str, tuple[Decimal, Decimal]]) -> None:
    """Σ余额表(借 − 贷) = Σ叶(余额表 − 序时账归到该叶) + 序时账(借 − 贷) − 未归到任何叶的序时账(借 − 贷)。"""
    by_leaf: dict[str, list[Leaf]] = {}
    for lf in leaves:
        by_leaf.setdefault(lf.code, []).append(lf)
    assigned: dict[str, Decimal] = {}
    orphans: list[dict] = []
    for code, (dr, cr) in ledger.items():
        leaf = next((code[:n] for n in range(len(code), 0, -1) if code[:n] in by_leaf), None)
        if leaf is None:
            orphans.append(_row(code, "", -(dr - cr), f"序时账 借 {_money(dr)} 贷 {_money(cr)}，科目余额表没有这个科目（或其上级）", journal=True))
        else:
            assigned[leaf] = assigned.get(leaf, _ZERO) + dr - cr
    rows = []
    for code, group in by_leaf.items():
        dr = sum((lf.debit for lf in group), _ZERO)
        cr = sum((lf.credit for lf in group), _ZERO)
        led = assigned.get(code, _ZERO)
        diff = dr - cr - led
        if abs(diff) >= EPS:
            ldr, lcr = _ledger_of(ledger, code)
            rows.append(_row(code, group[0].name, diff,
                             f"余额表 借 {_money(dr)} 贷 {_money(cr)}；序时账 借 {_money(ldr)} 贷 {_money(lcr)}", journal=True))
    src.add("ledger_mismatch", "科目余额表本期发生额与序时账不一致", sum((r["amount"] for r in rows), _ZERO), "balance", rows)
    total_dr = sum((v[0] for v in ledger.values()), _ZERO)
    total_cr = sum((v[1] for v in ledger.values()), _ZERO)
    src.add("journal_unbalanced", f"序时账本身借贷不平（借 {_money(total_dr)}、贷 {_money(total_cr)}）", total_dr - total_cr, "journal")
    src.add("journal_orphan", "序时账里有科目余额表没有的科目", sum((r["amount"] for r in orphans), _ZERO), "journal", orphans)


def _ledger_of(ledger: dict[str, tuple[Decimal, Decimal]], leaf: str) -> tuple[Decimal, Decimal]:
    dr = cr = _ZERO
    for code, (d, c) in ledger.items():
        if code.startswith(leaf):
            dr, cr = dr + d, cr + c
    return dr, cr


def explain_prior(
    *, view: list[dict], opening: dict[str, Decimal], leaves: list[Leaf], d_eff: Decimal, d_auto: Decimal, manual_rows: list[dict],
) -> list[dict]:
    """上年年末列（= 本年试算表期初）。"""
    src = _Sources()
    names = {r["standard_account_code"]: r["account_name"] for r in view}
    src.add("manual", "本页手工修改的金额", d_eff - d_auto, "statement", manual_rows)
    _coverage(src, opening, names, include_pl=True)

    live: dict[str, Decimal] = {}
    for lf in leaves:
        if lf.std is not None:
            live[lf.std] = live.get(lf.std, _ZERO) + lf.opening
    stale_rows, stale = [], _ZERO
    for code in sorted(set(opening) | set(live)):
        if is_pl_code(code):
            continue
        delta = opening.get(code, _ZERO) - live.get(code, _ZERO)
        if abs(delta) >= EPS:
            stale_rows.append(_row(code, names.get(code, ""), delta,
                                   f"试算表期初 {_money(opening.get(code, _ZERO))}，科目余额表期初 {_money(live.get(code, _ZERO))}（请点「重算试算表」）"))
            stale += delta
    src.add("tb_stale", "试算表期初与科目余额表期初不一致", stale, "trial_balance", stale_rows)

    unmapped = [lf for lf in leaves if lf.std is None and abs(lf.opening) >= EPS]
    src.add("unmapped", "有期初余额的客户科目没有映射到标准科目，没进试算表",
            -sum((lf.opening for lf in unmapped), _ZERO), "mapping",
            [_row(lf.code, lf.name, -lf.opening, f"期初余额 {_money(lf.opening)} 未映射") for lf in unmapped])
    pl = [lf for lf in leaves if lf.std is not None and is_pl_code(lf.std) and abs(lf.opening) >= EPS]
    src.add("pl_opening", "损益类科目有期初余额（上年没有结转）", -sum((lf.opening for lf in pl), _ZERO), "balance",
            [_row(lf.code, lf.name, -lf.opening, f"期初余额 {_money(lf.opening)}") for lf in pl])
    src.add("balance_opening", "科目余额表期初余额借贷不平", sum((lf.opening for lf in leaves), _ZERO), "balance")
    return src.result(d_eff)


def _manual_rows(saved: dict, col: str, eff: dict, auto: dict, idx: int) -> list[dict]:
    rows = []
    for key in (ASSETS_TOTAL[0], LIAB_EQUITY_TOTAL[0]):
        labels = {row["r"]: row["label"] for row in statement_def(key)["rows"]}
        for r, cols in (saved.get(key) or {}).items():
            if not isinstance(cols, dict) or col not in cols:
                continue
            line = int(r)
            v, a = eff[key][idx].get(line), auto[key][idx].get(line)
            rows.append({"code": "", "name": labels.get(line, ""), "amount": _d(v) - _d(a),
                         "note": f"手工值 {_money(_d(v))}，自动算出 {_money(_d(a))}",
                         "statement": key, "r": line, "column": col})
    return rows


def _diff(values: dict, idx: int) -> Decimal:
    return (values[ASSETS_TOTAL[0]][idx].get(ASSETS_TOTAL[1]) or _ZERO) - (values[LIAB_EQUITY_TOTAL[0]][idx].get(LIAB_EQUITY_TOTAL[1]) or _ZERO)


async def diagnose(
    db: AsyncSession, project_id: UUID, year: int, *, view: list[dict], closing: dict[str, Decimal], opening: dict[str, Decimal],
    pl_close: Decimal, values: dict, auto_values: dict, saved: dict, columns: list[str],
) -> dict[str, list[dict]]:
    """``columns``：不平的列（current / prior）→ 各列差额来源。"""
    leaves = await load_leaves(db, project_id, year)
    out: dict[str, list[dict]] = {}
    for col in columns:
        idx = 0 if col == "current" else 1
        d_eff, d_auto = _diff(values, idx), _diff(auto_values, idx)
        manual = _manual_rows(saved, col, values, auto_values, idx)
        if col == "current":
            ledger = await load_ledger(db, project_id, year) or None
            out[col] = explain_current(view=view, closing=closing, pl_close=pl_close, leaves=leaves, ledger=ledger,
                                       d_eff=d_eff, d_auto=d_auto, manual_rows=manual)
        else:
            out[col] = explain_prior(view=view, opening=opening, leaves=leaves, d_eff=d_eff, d_auto=d_auto, manual_rows=manual)
    return out


__all__ = ["Leaf", "coefficient", "diagnose", "explain_current", "explain_prior", "norm_code", "PL_CLOSE"]
