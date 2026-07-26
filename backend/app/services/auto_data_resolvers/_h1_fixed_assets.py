"""H1 固定资产 Auto Data Resolvers — 科目1601+1602 / 月度折旧发生额."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger
from app.services.auto_data_resolvers import auto_resolver
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

_H1_ACCOUNT_PREFIXES = ("1601", "1602")


@auto_resolver("h1_tb_unadjusted")
async def _resolve_h1_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 取科目1601固定资产+1602累计折旧的未审数.

    1601: 资产类/借方 — unadjusted_amount 为正数（期末余额）
    1602: 备抵类/贷方 — unadjusted_amount 为正数（期末余额，贷方方向）
    """
    cost_unadjusted = 0.0
    dep_unadjusted = 0.0
    cost_audited = 0.0
    dep_audited = 0.0

    try:
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1601%' OR standard_account_code LIKE '1602%')
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            if code.startswith("1601"):
                cost_unadjusted += float(row.unadjusted_amount or 0)
                cost_audited += float(row.audited_amount or 0)
            elif code.startswith("1602"):
                dep_unadjusted += float(row.unadjusted_amount or 0)
                dep_audited += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_tb_unadjusted resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    net_unadjusted = cost_unadjusted - dep_unadjusted
    summary = (
        f"H1: 1601原值未审={cost_unadjusted:,.0f}，"
        f"1602折旧未审={dep_unadjusted:,.0f}，"
        f"净值未审={net_unadjusted:,.0f}"
    )
    return {
        "summary": summary,
        "cost_unadjusted": cost_unadjusted,
        "dep_unadjusted": dep_unadjusted,
        "cost_audited": cost_audited,
        "dep_audited": dep_audited,
        "net_unadjusted": net_unadjusted,
        "account_codes": list(_H1_ACCOUNT_PREFIXES),
    }


@auto_resolver("h1_depreciation_monthly")
async def _resolve_h1_depreciation_monthly(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 tb_ledger 取月度折旧发生额（科目1602贷方发生=折旧计提）.

    折旧计提在贷方：每月贷方发生额即为当月折旧。
    """
    monthly: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    total = 0.0

    try:
        # 数据集隔离：tb_ledger 同项目可有 staged/active/superseded 多份，
        # 裸 is_deleted=false 会跨数据集重复累加折旧（铁律：四表查询统一 get_active_filter）。
        active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
        # 字段名为 voucher_date（原实现写 occurrence_date，该列不存在 → 查询恒失败被吞成"数据获取失败"）
        month_expr = sa.extract("month", TbLedger.voucher_date)
        result = await db.execute(
            sa.select(
                sa.cast(month_expr, sa.Integer).label("m"),
                sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("dep_amount"),
            )
            .where(
                active_filter,
                sa.extract("year", TbLedger.voucher_date) == year,
                TbLedger.account_code.like("1602%"),
            )
            .group_by(month_expr)
            .order_by(month_expr)
        )
        for row in result.fetchall():
            month_num = int(row.m)
            amt = float(row.dep_amount or 0)
            if 1 <= month_num <= 12:
                monthly[month_num] = amt
                total += amt
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_depreciation_monthly resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    summary = f"H1折旧月度: 合计={total:,.0f}，月均={total / 12:,.0f}"
    return {
        "summary": summary,
        "monthly": monthly,
        "total": total,
        "monthly_avg": round(total / 12, 2),
    }


_COUNTERPART_FILL_THRESHOLD = 0.8


@auto_resolver("h1_depreciation_by_counterpart")
async def _resolve_h1_depreciation_by_counterpart(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """按对方科目归集 1602 贷方折旧（H1-13 分配核对，Req3.4）。

    条件性取数：仅当序时账对方科目填充率 ≥ 阈值才返回分布；否则返回
    available=False + 中文原因（凭证多为合并记账，无法自动归属费用科目）。
    宁缺勿造——不足时不编造分布。
    """
    try:
        active_filter = await get_active_filter(db, TbLedger.__table__, project_id, year)
        probe = (
            await db.execute(
                sa.select(
                    sa.func.count().label("total"),
                    sa.func.count(
                        sa.case(
                            (
                                sa.and_(
                                    TbLedger.counterpart_account.isnot(None),
                                    sa.func.trim(TbLedger.counterpart_account) != "",
                                ),
                                1,
                            ),
                            else_=None,
                        )
                    ).label("filled"),
                ).where(active_filter, TbLedger.account_code.like("1602%"))
            )
        ).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_depreciation_by_counterpart probe failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "available": False, "_error": True}

    total = int(getattr(probe, "total", 0) or 0)
    filled = int(getattr(probe, "filled", 0) or 0)
    if total <= 0:
        return {"available": False, "reason": "序时账无 1602 折旧分录", "by_counterpart": []}
    fill_rate = filled / total
    if fill_rate < _COUNTERPART_FILL_THRESHOLD:
        return {
            "available": False,
            "fill_rate": round(fill_rate, 4),
            "total_lines": total,
            "reason": (
                f"序时账对方科目填充率仅 {fill_rate:.0%}（{filled}/{total} 条），"
                "且凭证多为合并记账，无法按费用科目自动归集折旧；请与 F5/F2/K8/K9/I6 对方底稿人工勾稽"
            ),
            "by_counterpart": [],
        }

    try:
        rows = (
            await db.execute(
                sa.select(
                    TbLedger.counterpart_account.label("cp"),
                    sa.func.coalesce(sa.func.sum(TbLedger.credit_amount), 0).label("amt"),
                )
                .where(active_filter, TbLedger.account_code.like("1602%"))
                .group_by(TbLedger.counterpart_account)
                .order_by(sa.func.sum(TbLedger.credit_amount).desc())
            )
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("h1_depreciation_by_counterpart group failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "available": False, "_error": True}

    dist = [
        {"counterpart": (r.cp or "").strip(), "amount": abs(float(r.amt or 0))}
        for r in rows
        if (r.cp or "").strip()
    ]
    return {
        "available": True,
        "fill_rate": round(fill_rate, 4),
        "by_counterpart": dist,
        "summary": f"H1折旧按对方科目分布：{len(dist)} 个科目",
    }
