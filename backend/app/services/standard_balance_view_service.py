"""标准科目余额视图：试算平衡表页（CITAR 版式）的「审定科目余额表」与「底稿取数余额表」。

试算表（trial_balance）只存期初 / 未审 / 调整净额 / 审定数，没有本期借贷发生额，
调整也只存净额。CITAR 版式要按「期初 → 本期借贷 + 借贷方审计调整 → 期末」分列，
本服务在读时补齐：

- 本期借方 / 贷方：tb_balance 叶子行经映射汇总到标准科目（与试算表未审数同一口径，
  见 tb_mapping_sql）
- 借方 / 贷方审计调整：已批准、非底稿来源的调整分录按借贷分别汇总
  （与 ``TrialBalanceService.recalc_adjustments`` 同一筛选，只是不轧差）
- 期初 / 审定数 / 底稿发布调整：直接取 trial_balance

金额一律「借正贷负」返回（前端按符号显示方向），不写库。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    Adjustment,
    AdjustmentEntry,
    TbBalance,
    TrialBalance,
)
from app.services.dataset_query import get_active_filter
from app.services.ledger_import.direction_resolver import resolve_account_direction
from app.services.tb_mapping_sql import leaf_condition, resolved_standard_code, signed_balance

_ZERO = Decimal("0")


def _d(value) -> Decimal:
    return Decimal(str(value)) if value is not None else _ZERO


def _signed_natural(amount: Decimal, direction: str) -> Decimal:
    """试算表的自然正数口径 → 借正贷负。"""
    return -amount if direction == "credit" else amount


async def _period_by_standard(db: AsyncSession, project_id: UUID, year: int) -> dict[str, dict]:
    """标准科目 → {debit, credit, closing}（tb_balance 叶子行经映射汇总）。"""
    bal = TbBalance.__table__
    sub = (
        sa.select(
            resolved_standard_code(bal).label("std"),
            bal.c.debit_amount.label("dr"),
            bal.c.credit_amount.label("cr"),
            signed_balance(bal.c.closing_balance, bal.c.closing_direction).label("sc"),
        )
        .select_from(bal)
        .where(await get_active_filter(db, bal, project_id, year))
        .where(leaf_condition(bal))
    ).subquery("period_sub")
    q = (
        sa.select(
            sub.c.std,
            sa.func.coalesce(sa.func.sum(sub.c.dr), 0).label("dr"),
            sa.func.coalesce(sa.func.sum(sub.c.cr), 0).label("cr"),
            sa.func.coalesce(sa.func.sum(sub.c.sc), 0).label("sc"),
        )
        .where(sub.c.std.isnot(None))
        .group_by(sub.c.std)
    )
    rows = (await db.execute(q)).fetchall()
    return {r.std: {"debit": _d(r.dr), "credit": _d(r.cr), "closing": _d(r.sc)} for r in rows}


async def _adjustments_by_standard(db: AsyncSession, project_id: UUID, year: int) -> dict[str, dict]:
    """标准科目 → {debit, credit}：已批准、非底稿来源的调整分录（借贷分别汇总，不轧差）。"""
    adj = Adjustment.__table__
    ae = AdjustmentEntry.__table__
    q = (
        sa.select(
            ae.c.standard_account_code.label("code"),
            sa.func.coalesce(sa.func.sum(ae.c.debit_amount), 0).label("dr"),
            sa.func.coalesce(sa.func.sum(ae.c.credit_amount), 0).label("cr"),
        )
        .select_from(ae.join(adj, ae.c.adjustment_id == adj.c.id))
        .where(
            adj.c.project_id == project_id,
            adj.c.year == year,
            adj.c.is_deleted == sa.false(),
            adj.c.review_status == "approved",
            # 底稿来源已由审定表发布体现在 wp_adjustment，再计入会双计（同 recalc_adjustments）
            sa.or_(adj.c.origin.is_(None), adj.c.origin != "workpaper"),
        )
        .group_by(ae.c.standard_account_code)
    )
    rows = (await db.execute(q)).fetchall()
    return {r.code: {"debit": _d(r.dr), "credit": _d(r.cr)} for r in rows if r.code}


async def _standard_names(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    """标准科目表名称（同码多行取最短，与 recalc_unadjusted 的兜底名同口径）。

    试算表的 account_name 优先取客户科目名（如「\\银行存款」挂在 1122 上），
    标准科目口径的视图应显示标准科目名。
    """
    ac = AccountChart.__table__
    rows = (
        await db.execute(
            sa.select(ac.c.account_code, ac.c.account_name).where(
                ac.c.project_id == project_id,
                ac.c.source == AccountSource.standard.value,
                ac.c.is_deleted == sa.false(),
            )
        )
    ).fetchall()
    names: dict[str, str] = {}
    for code, name in rows:
        if name and (code not in names or len(name) < len(names[code])):
            names[code] = name
    return names


async def build_standard_balance_view(
    db: AsyncSession, project_id: UUID, year: int, company_code: str = "001",
) -> list[dict]:
    """全部标准科目（含零余额行）的余额视图，按标准科目码排序。"""
    tb_rows = (
        await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == company_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
    ).scalars().all()
    period = await _period_by_standard(db, project_id, year)
    adjustments = await _adjustments_by_standard(db, project_id, year)
    standard_names = await _standard_names(db, project_id)

    by_code = {r.standard_account_code: r for r in tb_rows}
    codes = sorted(set(by_code) | set(period) | set(adjustments))

    result: list[dict] = []
    for code in codes:
        tb = by_code.get(code)
        tb_name = (tb.account_name if tb else None) or ""
        # 方向按试算表 GET 同一入参判定（与审定数的自然正数口径一致）；显示名用标准科目名
        direction, _ = resolve_account_direction(code, tb_name)
        name = standard_names.get(code) or tb_name
        p = period.get(code, {"debit": _ZERO, "credit": _ZERO, "closing": _ZERO})
        a = adjustments.get(code, {"debit": _ZERO, "credit": _ZERO})
        wp = _signed_natural(_d(tb.wp_adjustment), direction) if tb else _ZERO
        opening = _signed_natural(_d(tb.opening_balance), direction) if tb else _ZERO
        # 期末未审：tb_balance 叶子余额（损益类年末结转后通常为 0）；调整后 = 未审 + 借调 − 贷调 + 底稿发布调整
        closing = p["closing"]
        result.append({
            "standard_account_code": code,
            "account_name": name,
            "account_category": tb.account_category.value if tb and tb.account_category else None,
            "direction": direction,
            "opening_balance": str(opening),
            "period_debit": str(p["debit"]),
            "period_credit": str(p["credit"]),
            "adjustment_debit": str(a["debit"]),
            "adjustment_credit": str(a["credit"]),
            "wp_adjustment": str(wp),
            "closing_balance": str(closing),
            "adjusted_closing_balance": str(closing + a["debit"] - a["credit"] + wp),
            # 平台权威审定数（自然正数口径），底稿取数读的就是它
            "audited_amount": str(_d(tb.audited_amount)) if tb and tb.audited_amount is not None else None,
            "unadjusted_amount": str(_d(tb.unadjusted_amount)) if tb and tb.unadjusted_amount is not None else None,
            "in_trial_balance": tb is not None,
        })
    return result
