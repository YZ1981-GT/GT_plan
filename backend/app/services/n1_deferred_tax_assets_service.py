"""N1 递延所得税资产 — 业务逻辑服务

资产类取数（tb_balance期末余额，direction=借）+ 递延税资产测算 + 可弥补亏损确认 + 跨底稿合计。

提供功能：
- 资产类TB取数（tb_balance 期末余额，direction=借）
- 递延所得税资产测算（可抵扣暂时性差异×适用税率）
- 可弥补亏损确认（min(未弥补亏损, 预计未来应纳税所得额)×税率）
- 资产类期末余额校验（期末=期初+借方-贷方）
- 加权平均税率计算
- 审定数回写 trial_balance
- 跨底稿合计（N1资产部分 + N3负债部分，供N5核对）

科目1811递延所得税资产（借方/资产类）：期末=期初+借方-贷方
核心公式: 递延所得税资产 = 可抵扣暂时性差异 × 适用税率
可弥补亏损: 可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 税率

Requirements: 4.1-4.6, 5.1-5.6, 8.1-8.4
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_N1_ACCOUNT_CODE = "1811"


# ═══════════════════════════════════════════════════════════════════════════════
# 递延所得税资产测算引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_temporary_difference(book_value: float, tax_base: float) -> float:
    """暂时性差异 = 账面价值 - 计税基础

    资产项：账面 < 计税基础 → 可抵扣暂时性差异（产生递延所得税资产）
    资产项：账面 > 计税基础 → 应纳税暂时性差异（产生递延所得税负债→N3）

    Requirements: 4.2
    """
    return book_value - tax_base


def calc_deferred_tax(temp_diff: float, tax_rate: float) -> float:
    """递延所得税 = 暂时性差异 × 适用税率

    结果四舍五入到2位小数。
    对于N1（可抵扣差异为负值），结果取绝对值表示递延税资产。

    Requirements: 4.3
    """
    return round(temp_diff * tax_rate, 2)


def calc_deferred_tax_asset(deductible_diff: float, tax_rate: float) -> float:
    """递延所得税资产 = 可抵扣暂时性差异 × 适用税率

    deductible_diff 应为正值（可抵扣暂时性差异绝对值）。
    结果四舍五入到2位小数。

    Requirements: 4.3
    """
    return round(deductible_diff * tax_rate, 2)


def calc_weighted_avg_rate(tax_amounts: list[float], diffs: list[float]) -> float:
    """加权平均税率 = Σ递延税资产 / Σ可抵扣暂时性差异

    当差异合计为0时返回0.0（避免除零）。

    Requirements: 4.3
    """
    total_diff = sum(diffs)
    if total_diff == 0:
        return 0.0
    total_tax = sum(tax_amounts)
    return total_tax / total_diff


def classify_temporary_differences(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """将暂时性差异分类为可抵扣（→N1资产）和应纳税（→N3负债）

    分类规则：
    - 资产项账面 < 计税基础 → 可抵扣暂时性差异 → 递延所得税资产(N1)
    - 资产项账面 > 计税基础 → 应纳税暂时性差异 → 递延所得税负债(N3)

    Requirements: 4.4
    """
    deductible: list[dict[str, Any]] = []  # 可抵扣 → N1
    taxable: list[dict[str, Any]] = []  # 应纳税 → N3

    for row in rows:
        book_value = _parse_num(row.get("bookValue", 0))
        tax_base = _parse_num(row.get("taxBase", 0))
        diff = book_value - tax_base

        classified = {**row, "temporaryDifference": diff}
        if diff < 0:
            # 账面 < 计税基础 → 可抵扣
            classified["deductibleDiff"] = abs(diff)
            deductible.append(classified)
        elif diff > 0:
            # 账面 > 计税基础 → 应纳税
            classified["taxableDiff"] = diff
            taxable.append(classified)
        # diff == 0 → 无暂时性差异，不归入任何一方

    return {"deductible": deductible, "taxable": taxable}


# ═══════════════════════════════════════════════════════════════════════════════
# 可弥补亏损确认引擎（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_unrecovered_loss(loss_amount: float, recovered: float) -> float:
    """未弥补亏损 = 亏损金额 - 已弥补金额

    结果不能为负（已弥补不能超过亏损金额）。

    Requirements: 5.2
    """
    return max(0.0, loss_amount - recovered)


def calc_recognizable_asset(
    unrecovered: float, future_taxable_income: float, tax_rate: float
) -> float:
    """可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 税率

    遵循谨慎性原则：以预计未来应纳税所得额为限确认。

    Requirements: 5.2, 5.4
    """
    recognizable_base = min(unrecovered, future_taxable_income)
    return round(recognizable_base * tax_rate, 2)


def is_compensation_expired(
    loss_year: int, current_year: int, max_years: int = 5
) -> bool:
    """判断弥补期限是否届满

    一般企业弥补期限5年，高新技术企业/科技型中小企业10年。

    Requirements: 5.3
    """
    return (current_year - loss_year) > max_years


def calc_loss_recognition(
    losses: list[dict[str, Any]],
    future_taxable_income: float,
    tax_rate: float,
) -> dict[str, Any]:
    """可弥补亏损批量确认计算

    逐年计算未弥补亏损，汇总可确认递延税资产总额。
    已过期亏损不确认。

    losses 结构: [{"lossYear": int, "lossAmount": float, "recovered": float,
                   "maxYears": int(可选,默认5)}]

    Requirements: 5.1-5.6
    """
    import datetime

    current_year = datetime.date.today().year
    details: list[dict[str, Any]] = []
    total_unrecovered = 0.0
    total_recognizable = 0.0
    remaining_income = future_taxable_income

    for loss in losses:
        loss_year = int(loss.get("lossYear", 0))
        loss_amount = _parse_num(loss.get("lossAmount", 0))
        recovered = _parse_num(loss.get("recovered", 0))
        max_years = int(loss.get("maxYears", 5))

        unrecovered = calc_unrecovered_loss(loss_amount, recovered)
        expired = is_compensation_expired(loss_year, current_year, max_years)

        if expired or unrecovered <= 0:
            details.append({
                "lossYear": loss_year,
                "lossAmount": loss_amount,
                "recovered": recovered,
                "unrecovered": unrecovered,
                "expired": expired,
                "recognizable": 0.0,
                "recognizableAsset": 0.0,
            })
            continue

        # 按剩余可用所得额限额确认
        recognizable_base = min(unrecovered, remaining_income)
        recognizable_asset = round(recognizable_base * tax_rate, 2)

        total_unrecovered += unrecovered
        total_recognizable += recognizable_asset
        remaining_income = max(0.0, remaining_income - recognizable_base)

        details.append({
            "lossYear": loss_year,
            "lossAmount": loss_amount,
            "recovered": recovered,
            "unrecovered": unrecovered,
            "expired": False,
            "recognizable": recognizable_base,
            "recognizableAsset": recognizable_asset,
        })

    return {
        "details": details,
        "totalUnrecovered": round(total_unrecovered, 2),
        "totalRecognizable": round(total_recognizable, 2),
        "futureTaxableIncome": future_taxable_income,
        "taxRate": tax_rate,
        "insufficientWarning": total_unrecovered > future_taxable_income,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 资产类公式（纯函数）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_asset_end_balance(begin: float, debit: float, credit: float) -> float:
    """资产类期末余额 = 期初 + 借方 - 贷方（1811借方科目）

    Requirements: 8.1
    """
    return begin + debit - credit


def calc_audited_amount(unadjusted: float, aje: float, rje: float) -> float:
    """审定数 = 未审数 + AJE + RJE

    Requirements: 4.1
    """
    return unadjusted + aje + rje


def calc_subtotal(arr: list[float]) -> float:
    """合计 = Σarr

    Requirements: 4.1
    """
    return sum(arr)


def calc_proportion(item: float, total: float) -> float:
    """占比 = item / total

    total=0 时返回 0.0（避免除零）。

    Requirements: 4.3
    """
    if total == 0:
        return 0.0
    return item / total


def validate_asset_direction(
    begin: float,
    debit: float,
    credit: float,
    reported_end: float | None = None,
) -> dict[str, Any]:
    """校验资产类借方公式方向

    资产类借方：期末 = 期初 + 借方 − 贷方

    Requirements: 8.1, 8.4
    """
    expected = calc_asset_end_balance(begin, debit, credit)
    result: dict[str, Any] = {
        "expected": round(expected, 2),
        "formula": "期末=期初+借方-贷方（资产类借方）",
        "direction": "debit",
        "account_code": _N1_ACCOUNT_CODE,
    }

    if reported_end is not None:
        diff = reported_end - expected
        result["reported"] = reported_end
        result["difference"] = round(diff, 2)
        result["isValid"] = abs(diff) <= 0.01

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# TB 取数 + 回写
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


async def _resolve_year(project_id: str, db: Any, year: int | None) -> int:
    """解析审计年度：显式传入优先，否则取 projects.audit_year（缺失回退 0）。"""
    if year is not None:
        return int(year)
    import sqlalchemy as sa

    try:
        row = (
            await db.execute(
                sa.text("SELECT audit_year FROM projects WHERE id = :pid"),
                {"pid": str(project_id)},
            )
        ).fetchone()
        if row and row.audit_year:
            return int(row.audit_year)
    except Exception as e:  # noqa: BLE001
        logger.warning("N1 service: 审计年度解析失败 project_id=%s: %s", project_id, e)
    return 0


async def get_tb_balance_for_n1(
    project_id: str, db: Any, year: int | None = None
) -> dict[str, Any]:
    """从 tb_balance 取科目1811递延所得税资产余额数据（资产类/借方）

    ⚠️ DEPRECATED（无调用方）：N1 的 TB 取数已由 render 策略
    `wp_render_strategies/_n1_deferred_tax_assets.py` 直接完成并随 render-config 下发，
    本函数无任何 router/服务调用方。保留仅为兼容外部脚本，勿在新代码中引用。

    资产类取数规则：从tb_balance取期末余额（direction=借）。
    期末余额 = 期初 + 本期借方 - 本期贷方。

    ⚠️ tb_balance 真实列名为 opening_balance / closing_balance / account_code
    （无 begin_balance / end_balance / standard_account_code）。

    Requirements: 8.2, 8.3
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    result: dict[str, Any] = {
        "account_code": _N1_ACCOUNT_CODE,
        "account_name": "递延所得税资产",
        "direction": "debit",
        "begin_balance": 0.0,
        "debit_amount": 0.0,
        "credit_amount": 0.0,
        "end_balance": 0.0,
        "found": False,
    }

    try:
        resolved_year = await _resolve_year(project_id, db, year)
        active_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, resolved_year
        )
        stmt = (
            sa.select(
                TbBalance.opening_balance.label("begin_balance"),
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_balance.label("end_balance"),
            )
            .where(
                TbBalance.account_code == _N1_ACCOUNT_CODE,
                active_filter,
            )
            .limit(1)
        )
        row = (await db.execute(stmt)).fetchone()
        if row:
            result["begin_balance"] = _parse_num(row.begin_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.end_balance)
            result["found"] = True
    except Exception as e:  # noqa: BLE001
        logger.warning("N1 service: TB 取数失败 project_id=%s: %s", project_id, e)

    return result


async def writeback_tb(
    project_id: str, audited_amount: float, db: Any, year: int | None = None
) -> dict[str, Any]:
    """回写审定数到 trial_balance（科目1811，期末余额，借方/资产类）

    ⚠️ DEPRECATED（无调用方）：前端 N1-1 的 TB 回写走平台标准端点
    `PUT /api/projects/{pid}/trial-balance/writeback`（trial_balance_service，
    含数据集/口径/审计留痕）。本函数是绕过该服务的裸 SQL 旁路，无调用方，勿新引用。

    ⚠️ trial_balance 是分年度存储，必须带 year 过滤（否则跨年度全表更新）。

    Requirements: 8.3
    """
    import sqlalchemy as sa

    try:
        resolved_year = await _resolve_year(project_id, db, year)
        result = await db.execute(
            sa.text(
                "UPDATE trial_balance "
                "SET audited_amount = :amount "
                "WHERE project_id = :pid AND year = :year "
                "AND standard_account_code = :code"
            ),
            {
                "amount": audited_amount,
                "pid": str(project_id),
                "year": resolved_year,
                "code": _N1_ACCOUNT_CODE,
            },
        )
        await db.flush()
        return {
            "success": True,
            "account_code": _N1_ACCOUNT_CODE,
            "audited_amount": audited_amount,
            "rows_affected": result.rowcount,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("N1 service: TB 回写失败 project_id=%s: %s", project_id, e)
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 跨底稿合计（N1+N3联动，供N5递延所得税费用核对）
# ═══════════════════════════════════════════════════════════════════════════════


async def get_cross_workpaper_totals(
    project_id: str, db: Any, year: int | None = None
) -> dict[str, Any]:
    """跨底稿合计：N1资产部分 + N3负债部分

    ⚠️ DEPRECATED（无调用方）：N1↔N3↔N5 的跨底稿合计已由前端
    `useN1CrossSheet` / `useN5DeferredReconcile` 经 checklist_responses 键完成。
    本函数无 router 调用方，勿在新代码中引用。

    从 tb_balance 获取 N1 资产数据和 N3 负债数据，
    供 N5 递延所得税费用核对行（N5-8）消费。

    递延所得税费用 = 本期递延税负债增加（N3本期变动）
                    - 本期递延税资产增加（N1本期变动）

    Requirements: 4.4, 4.6
    """
    import sqlalchemy as sa

    from app.models.audit_platform_models import TbBalance
    from app.services.dataset_query import get_active_filter

    _N3_ACCOUNT_CODE = "2901"

    n1_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }
    n3_data: dict[str, float] = {
        "begin_balance": 0.0,
        "end_balance": 0.0,
        "period_change": 0.0,
    }

    try:
        resolved_year = await _resolve_year(project_id, db, year)
        active_filter = await get_active_filter(
            db, TbBalance.__table__, project_id, resolved_year
        )

        # N1 递延所得税资产（科目1811，资产类借方）
        n1_row = (
            await db.execute(
                sa.select(
                    TbBalance.opening_balance.label("begin_balance"),
                    TbBalance.closing_balance.label("end_balance"),
                )
                .where(
                    TbBalance.account_code == _N1_ACCOUNT_CODE,
                    active_filter,
                )
                .limit(1)
            )
        ).fetchone()

        if n1_row:
            n1_begin = _parse_num(n1_row.begin_balance)
            n1_end = _parse_num(n1_row.end_balance)
            n1_data["begin_balance"] = n1_begin
            n1_data["end_balance"] = n1_end
            n1_data["period_change"] = n1_end - n1_begin

        # N3 递延所得税负债（科目2901，负债类贷方）
        n3_row = (
            await db.execute(
                sa.select(
                    TbBalance.opening_balance.label("begin_balance"),
                    TbBalance.closing_balance.label("end_balance"),
                )
                .where(
                    TbBalance.account_code == _N3_ACCOUNT_CODE,
                    active_filter,
                )
                .limit(1)
            )
        ).fetchone()

        if n3_row:
            n3_begin = _parse_num(n3_row.begin_balance)
            n3_end = _parse_num(n3_row.end_balance)
            n3_data["begin_balance"] = n3_begin
            n3_data["end_balance"] = n3_end
            n3_data["period_change"] = n3_end - n3_begin

    except Exception as e:  # noqa: BLE001
        logger.warning("N1 service: 跨底稿合计查询失败: %s", e)

    # 递延所得税费用 = 本期递延税负债增加 - 本期递延税资产增加
    deferred_tax_expense = n3_data["period_change"] - n1_data["period_change"]

    return {
        "project_id": str(project_id),
        "n1_asset": n1_data,
        "n3_liability": n3_data,
        "deferred_tax_expense": round(deferred_tax_expense, 2),
        "source": "N1-递延所得税资产 + N3-递延所得税负债",
        "target": "N5-8-递延所得税费用核对",
        "direction": "debit",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出
# ═══════════════════════════════════════════════════════════════════════════════
# N1-2 明细表的导入导出统一由 app/routers/n1_deferred_tax_assets.py 承载
# （表头/字段/item_id/存储列与前端 useN1Detail 对齐）。
# 此处原有第二套实现（item_id 拼成 "N1-N1-2-rows"、字段名与前端不一致、
# INSERT 漏 project_id）为死代码且会误导后续维护，已删除。
