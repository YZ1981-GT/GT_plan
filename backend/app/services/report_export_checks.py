"""财务报表交付导出提醒（不阻断导出）。

spec ``deliverable-trio-generation-accuracy`` AC-1.5 / AC-2.2：导出件与报表模块不一致、
数据缺失时必须作为提醒返回，不得静默。全部检查 fail-open（单项失败只跳过该项）。
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from app.services.report_template_binding import (
    BindingResult,
    TemplateSlots,
    code_family,
    load_template_slots,
    normalize_row_label,
    period_columns,
)

logger = logging.getLogger(__name__)

_TOL = Decimal("0.01")
#: 导出后核对的模板自算合计行（按规范化行名）
_CHECK_TOTALS = {
    "BS": ("流动资产合计", "非流动资产合计", "资产总计", "流动负债合计", "非流动负债合计", "负债合计",
           "所有者权益合计", "股东权益合计", "负债和所有者权益总计", "负债和股东权益总计"),
    "IS": ("营业利润", "利润总额", "净利润"),
}
_ASSET_TOTAL = ("资产总计",)
_LIAB_EQ_TOTAL = ("负债和所有者权益总计", "负债和股东权益总计", "负债及所有者权益总计")


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _fmt(v: Decimal | None) -> str:
    return "空" if v is None else f"{v:,.2f}"


def _labelled_values(wb, slots: TemplateSlots, family: str) -> dict[str, list[tuple[Decimal | None, Decimal | None]]]:
    """某族 sheet 中「规范化行名 → [(本期, 上期)]」（导出件 flatten 后的值）。"""
    out: dict[str, list[tuple[Decimal | None, Decimal | None]]] = {}
    for ws in wb.worksheets:
        if slots.sheet_family.get(ws.title) != family:
            continue
        cur_col, prior_col = period_columns(ws)
        if cur_col is None:
            continue
        for (sheet, row_no), label in slots.row_labels.items():
            if sheet != ws.title:
                continue
            key, _m = normalize_row_label(label)
            cur = _dec(ws.cell(row_no, cur_col).value)
            pri = _dec(ws.cell(row_no, prior_col).value) if prior_col else None
            out.setdefault(key, []).append((cur, pri))
    return out


def _db_values_by_key(report_data: dict[str, list[dict]], family: str) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = {}
    for rows in report_data.values():
        for r in rows:
            if code_family(r.get("row_code")) != family:
                continue
            key, _m = normalize_row_label(r.get("row_name"))
            v = _dec(r.get("current_period_amount"))
            if v is not None:
                out.setdefault(key, []).append(v)
    return out


def _check_balance(values: dict[str, list[tuple[Decimal | None, Decimal | None]]]) -> list[str]:
    def first(keys):
        for k in keys:
            if values.get(k):
                return values[k][0]
        return None

    a, le = first(_ASSET_TOTAL), first(_LIAB_EQ_TOTAL)
    if not a or not le:
        return []
    out = []
    for idx, label in ((0, "期末"), (1, "期初")):
        x, y = a[idx], le[idx]
        if x is None or y is None or (x == 0 and y == 0):
            continue
        if abs(x - y) > _TOL:
            out.append(
                f"资产负债表{label}不平衡：资产总计 {_fmt(x)}，负债和所有者权益总计 {_fmt(y)}，"
                f"差额 {_fmt(x - y)}。请先在报表模块核对报表行公式与试算表。"
            )
    return out


def _check_totals(values, db_by_key, family: str) -> list[str]:
    out: list[str] = []
    for key in _CHECK_TOTALS.get(family, ()):
        exported = values.get(key)
        db_vals = [v for v in db_by_key.get(key, []) if v != 0]
        if not exported or not db_vals:
            continue
        cur = exported[0][0]
        if cur is None:
            continue
        if not any(abs(cur - v) <= _TOL for v in db_vals):
            out.append(
                f"「{key}」导出 {_fmt(cur)}，报表模块为 {'/'.join(_fmt(v) for v in db_vals[:2])}："
                "报表明细行与模板行未完全对应，或报表合计公式口径不同，请核对。"
            )
    return out[:6]


async def collect_report_export_warnings(
    db,
    *,
    project_id: UUID,
    year: int,
    mode: str,
    wb,
    report_data: dict[str, list[dict]],
    binding: BindingResult | None,
    template_key: str,
    formulas_flattened: bool,
    slots: TemplateSlots | None = None,
) -> list[str]:
    """返回中文提醒列表（去重保序）。``slots`` 缺省时按变体读 manifest 模板。"""
    warnings: list[str] = []

    def add(items):
        for w in items:
            if w and w not in warnings:
                warnings.append(w)

    if slots is None:
        try:
            slots = load_template_slots(template_key)
        except Exception:  # noqa: BLE001
            logger.warning("导出提醒：读取模板出现位失败", exc_info=True)

    # 1. 平衡 / 合计核对（只在公式已 flatten 成值时可读）
    if slots is not None and formulas_flattened:
        try:
            for fam in ("BS", "IS"):
                vals = _labelled_values(wb, slots, fam)
                if fam == "BS":
                    add(_check_balance(vals))
                    add(_check_equity_vs_bs(wb, slots, vals))
                add(_check_totals(vals, _db_values_by_key(report_data, fam), fam))
        except Exception:  # noqa: BLE001
            logger.warning("导出提醒：合计核对失败", exc_info=True)

    # 2. 有金额但未导出的报表行
    if binding is not None and binding.unbound_nonzero:
        head = "、".join(
            f"{(r.get('row_name') or r.get('row_code') or '').strip()}（{_fmt(_dec(r.get('current_period_amount')))}）"
            for r in binding.unbound_nonzero[:5]
        )
        more = f" 等 {len(binding.unbound_nonzero)} 行" if len(binding.unbound_nonzero) > 5 else ""
        add([f"以下报表行有金额但模板无对应行、未导出：{head}{more}。"])

    # 3. 上期 / 期初来源
    try:
        add(_check_prior(report_data))
    except Exception:  # noqa: BLE001
        logger.warning("导出提醒：上期核对失败", exc_info=True)

    # 4. 现金流量表无数据
    try:
        cfs = report_data.get("cash_flow_statement") or []
        bs = report_data.get("balance_sheet") or []
        if cfs and bs and not any(_dec(r.get("current_period_amount")) for r in cfs) \
                and any(_dec(r.get("current_period_amount")) for r in bs):
            add(["现金流量表无数据（报表各行均为 0）：请先在现金流量表模块编制后重新生成报表。"])
    except Exception:  # noqa: BLE001
        logger.warning("导出提醒：现金流量表核对失败", exc_info=True)

    # 5. 减值表本期增减无来源 / 减值表全零而利润表有减值损失
    imp = report_data.get("impairment_provision") or []
    if any(_dec(r.get("current_period_amount")) for r in imp):
        add(["资产减值准备情况表本期计提 / 转回 / 转销无数据来源，已只填年初与期末余额，请补充本期增减变动。"])
    try:
        add(_check_impairment_source(report_data))
    except Exception:  # noqa: BLE001
        logger.warning("导出提醒：减值表来源核对失败", exc_info=True)

    # 6. 审定报表过期 / 旧布局
    if mode != "unadjusted":
        try:
            # SAVEPOINT：读失败只回滚自身，不让 PG 事务 aborted 连累导出后的落库
            async with db.begin_nested():
                add(await _check_freshness(db, project_id, year))
        except Exception:  # noqa: BLE001
            logger.warning("导出提醒：报表新鲜度核对失败", exc_info=True)
    return warnings


_EQ_TOTAL_HEADS = ("所有者权益合计", "股东权益合计", "所有者权益(或股东权益)合计", "股东权益(或所有者权益)合计")


def _first(values: dict[str, list[tuple[Decimal | None, Decimal | None]]], keys) -> tuple[Decimal | None, Decimal | None] | None:
    for k in keys:
        if values.get(k):
            return values[k][0]
    return None


def _check_equity_vs_bs(wb, slots: TemplateSlots, bs_values) -> list[str]:
    """权益变动表「本年年末余额 / 本年年初余额」合计列 ↔ 资产负债表所有者权益合计期末 / 期初。"""
    bs_eq = _first(bs_values, ("所有者权益合计", "股东权益合计"))
    if not bs_eq:
        return []
    out: list[str] = []
    for ws in wb.worksheets:
        if slots.sheet_family.get(ws.title) != "EQ" or "母公司" in ws.title:
            continue
        total_col = None
        for row in ws.iter_rows(min_row=1, max_row=8):
            for c in row:
                if isinstance(c.value, str) and normalize_row_label(c.value)[0] in _EQ_TOTAL_HEADS:
                    total_col = c.column
                    break
            if total_col:
                break
        if total_col is None:
            continue
        rows_by_key: dict[str, int] = {}
        for (sheet, row_no), label in slots.row_labels.items():
            if sheet == ws.title:
                rows_by_key.setdefault(normalize_row_label(label)[0], row_no)
        for key, idx, what in (("本年年末余额", 0, "年末"), ("本年年初余额", 1, "年初")):
            row_no = rows_by_key.get(key)
            bs_v = bs_eq[idx]
            if row_no is None or bs_v is None:
                continue
            eq_v = _dec(ws.cell(row_no, total_col).value)
            if eq_v is None or (eq_v == 0 and bs_v == 0):
                continue
            if abs(eq_v - bs_v) > _TOL:
                out.append(
                    f"所有者权益变动表「本年{what}余额」合计 {_fmt(eq_v)} 与资产负债表所有者权益合计"
                    f"{'期末' if idx == 0 else '期初'} {_fmt(bs_v)} 不一致（差额 {_fmt(eq_v - bs_v)}）："
                    "请在报表模块核对权益变动表（利润分配、其他权益变动等是否已编制）。"
                )
        break
    return out


def _check_impairment_source(report_data: dict[str, list[dict]]) -> list[str]:
    """减值准备情况表全为 0，而利润表有信用 / 资产减值损失：多为减值表取数公式未取到明细科目。"""
    imp = report_data.get("impairment_provision") or []
    if not imp or any(_dec(r.get("current_period_amount")) or _dec(r.get("prior_period_amount")) for r in imp):
        return []
    hits = []
    for r in report_data.get("income_statement") or []:
        key, _m = normalize_row_label(r.get("row_name"))
        if key in ("信用减值损失", "资产减值损失") and _dec(r.get("current_period_amount")):
            hits.append(f"{key} {_fmt(_dec(r.get('current_period_amount')))}")
    if not hits:
        return []
    return [
        "资产减值准备情况表各行均为 0，但利润表" + "、".join(dict.fromkeys(hits)) +
        "：请在报表模块检查减值准备表取数公式（如坏账准备只在明细科目有余额）。"
    ]


def _check_prior(report_data: dict[str, list[dict]]) -> list[str]:
    out: list[str] = []
    bs = report_data.get("balance_sheet") or []
    if bs and any(_dec(r.get("current_period_amount")) for r in bs):
        priors = [_dec(r.get("prior_period_amount")) for r in bs]
        if not any(p for p in priors):
            out.append(
                "资产负债表期初余额为空：期初应取本年试算表期初数，请在报表模块重新生成报表后再导出。"
            )
    is_rows = report_data.get("income_statement") or []
    if is_rows and any(_dec(r.get("current_period_amount")) for r in is_rows):
        if not any(_dec(r.get("prior_period_amount")) for r in is_rows):
            out.append("利润表上期金额无来源（未找到上年项目报表或试算表），已留空，请补充。")
    return out


async def _check_freshness(db, project_id: UUID, year: int) -> list[str]:
    from app.models.report_models import FinancialReport, ReportConfig
    from app.services.report_config_service import ReportConfigService

    out: list[str] = []
    stale = (
        await db.execute(
            sa.select(sa.func.count()).select_from(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
                FinancialReport.is_stale == sa.true(),
            )
        )
    ).scalar_one()
    if stale:
        out.append(f"报表有 {stale} 行已过期（上游数据已变更）：请先在报表模块重新生成报表。")

    standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
    codes = set(
        (
            await db.execute(
                sa.select(ReportConfig.row_code).where(
                    ReportConfig.applicable_standard == standard,
                    ReportConfig.is_deleted == sa.false(),
                )
            )
        ).scalars().all()
    )
    rows = (
        await db.execute(
            sa.select(FinancialReport.row_code).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )
    ).scalars().all()
    if codes and rows:
        missing = sum(1 for c in set(codes) if c not in set(rows))
        if missing > len(codes) * 0.2:
            out.append(
                f"报表数据为旧版行次布局（现行配置 {len(codes)} 行中 {missing} 行未生成）："
                "请在报表模块重新生成报表后再导出。"
            )
    return out
