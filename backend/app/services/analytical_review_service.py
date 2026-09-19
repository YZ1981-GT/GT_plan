"""分析性复核数据服务 — 横向/纵向趋势分析 + 变动状况判定

从 financial_report 表按 row_code 取本年/上年审定数，计算变动额/变动%/变动状况，
组装 BS 横向/纵向 + IS 横向/纵向 四个维度的前端数据结构。

Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Materiality
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 阈值常量
# ---------------------------------------------------------------------------
SIGNIFICANT_PCT_THRESHOLD = Decimal("20")  # 变动% > 20% → significant
ATTENTION_PCT_THRESHOLD = Decimal("10")    # 变动% > 10% → attention


# ---------------------------------------------------------------------------
# 变动状况判定
# ---------------------------------------------------------------------------
def classify_change(
    change_pct: Decimal | None,
    change_amount: Decimal,
    materiality: Decimal,
) -> str:
    """根据变动%和变动额判定变动状况。

    - significant: |变动%| > 20% 或 |变动额| > 重要性水平
    - attention: |变动%| > 10%
    - normal: 其他
    """
    abs_change = abs(change_amount)
    if abs_change > materiality:
        return "significant"
    if change_pct is not None and abs(change_pct) > SIGNIFICANT_PCT_THRESHOLD:
        return "significant"
    if change_pct is not None and abs(change_pct) > ATTENTION_PCT_THRESHOLD:
        return "attention"
    return "normal"


# ---------------------------------------------------------------------------
# 变动计算
# ---------------------------------------------------------------------------
def compute_change(
    current: Decimal | None, prior: Decimal | None
) -> tuple[Decimal, Decimal | None]:
    """计算变动额和变动%。

    Returns:
        (change, change_pct) — change_pct 为 None 表示上年为 0 无法计算
    """
    cur = current or Decimal("0")
    pri = prior or Decimal("0")
    change = cur - pri
    if pri == 0:
        change_pct = None
    else:
        change_pct = change / abs(pri) * Decimal("100")
    return change, change_pct


# ---------------------------------------------------------------------------
# 纵向分析：比重%计算
# ---------------------------------------------------------------------------
def compute_weight_pct(amount: Decimal | None, total: Decimal | None) -> Decimal | None:
    """计算比重%：科目金额 / 合计金额 * 100"""
    if total is None or total == 0:
        return None
    amt = amount or Decimal("0")
    return amt / abs(total) * Decimal("100")


# ---------------------------------------------------------------------------
# 变动原因引用接口（预留）
# ---------------------------------------------------------------------------
async def get_audit_explanation_for_row(
    db: AsyncSession, project_id: UUID, year: int, row_code: str
) -> str | None:
    """从对应科目底稿的审定表审计说明中获取变动原因（预留接口）。

    当前返回 None（各科目底稿未修订完成）。
    后续实现：按 row_code → account_codes → wp_code 映射找到审定表，
    读取其 audit_explanation 字段。
    """
    return None  # TODO: 各科目底稿修订完成后实现


async def _get_is_listed(db: AsyncSession, project_id: UUID) -> bool:
    """判断项目是否为上市公司（template_type == 'listed'）。"""
    result = await db.execute(
        sa.text("SELECT template_type FROM projects WHERE id = :pid"),
        {"pid": str(project_id)},
    )
    return result.scalar_one_or_none() == "listed"


async def build_industry_comparison(
    db: AsyncSession, project_id: UUID, wp_code: str, year: int
) -> dict:
    """构建同行业对比分析 sheet 结构（A1-14-6，用户填写数据）。

    从 field_overrides 读取用户持久化的可比公司数据，合并到空模板结构上。
    scope = "analytical_review:industry_comparison:{project_id}"
    """
    from app.services.field_override_service import FieldOverrideService

    years = [year - 2, year - 1, year]
    scope = f"analytical_review:industry_comparison:{project_id}"
    override_svc = FieldOverrideService(db)
    overrides = await override_svc.get_batch(project_id, year, scope)

    # 构建公司列表（从 overrides 读取用户填写的名称/代码）
    companies = []
    for label in ["A", "B", "C", "D", "E"]:
        co_data = overrides.get(f"company:{label}", {})
        companies.append({
            "key": label,
            "name": co_data.get("name", "") or "",
            "stock_code": co_data.get("stock_code", "") or "",
        })

    # 构建指标网格（从 overrides 读取用户填写的数值）
    financial_data = {}
    for key, _ in _INDUSTRY_FINANCIAL_METRICS:
        financial_data[key] = {}
        for y in years:
            financial_data[key][str(y)] = {}
            for co_label in _COMPANY_LABELS:
                override_key = f"financial:{key}:{y}:{co_label}"
                val = overrides.get(override_key, {}).get("value")
                financial_data[key][str(y)][co_label] = val

    comparison_table = {}
    for key, _ in _INDUSTRY_COMPARISON_METRICS:
        comparison_table[key] = {}
        for y in years:
            comparison_table[key][str(y)] = {}
            for co_label in _COMPANY_LABELS:
                override_key = f"comparison:{key}:{y}:{co_label}"
                val = overrides.get(override_key, {}).get("value")
                comparison_table[key][str(y)][co_label] = val

    # 数据来源标注
    data_source_note = overrides.get("data_source_note", {}).get("value", "") or ""

    return {
        "title": "同行业对比分析",
        "index": f"{wp_code}-6",
        "years": years,
        "companies": companies,
        "financial_data": financial_data,
        "comparison_table": comparison_table,
        "financial_metric_labels": {k: v for k, v in _INDUSTRY_FINANCIAL_METRICS},
        "comparison_metric_labels": {k: v for k, v in _INDUSTRY_COMPARISON_METRICS},
        "data_source_note": data_source_note,
    }


async def save_industry_comparison(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    payload: dict,
    user_id: UUID | None = None,
) -> None:
    """保存同行业对比分析用户填写数据到 field_overrides。

    payload 结构:
    {
      "companies": [{"key": "A", "name": "...", "stock_code": "..."}],
      "financial_data": {metric_key: {year_str: {co_label: value}}},
      "comparison_table": {metric_key: {year_str: {co_label: value}}},
      "data_source_note": "..."
    }
    """
    from app.services.field_override_service import FieldOverrideService

    scope = f"analytical_review:industry_comparison:{project_id}"
    override_svc = FieldOverrideService(db)

    # 保存公司信息
    companies = payload.get("companies", [])
    for co in companies:
        label = co.get("key", "")
        if label:
            await override_svc.set(
                project_id, year, scope, f"company:{label}", "name",
                co.get("name", ""), user_id
            )
            await override_svc.set(
                project_id, year, scope, f"company:{label}", "stock_code",
                co.get("stock_code", ""), user_id
            )

    # 保存财务数据
    financial_data = payload.get("financial_data", {})
    for metric_key, year_data in financial_data.items():
        if not isinstance(year_data, dict):
            continue
        for year_str, co_data in year_data.items():
            if not isinstance(co_data, dict):
                continue
            for co_label, value in co_data.items():
                await override_svc.set(
                    project_id, year, scope,
                    f"financial:{metric_key}:{year_str}:{co_label}",
                    "value", value, user_id
                )

    # 保存对比分析表
    comparison_table = payload.get("comparison_table", {})
    for metric_key, year_data in comparison_table.items():
        if not isinstance(year_data, dict):
            continue
        for year_str, co_data in year_data.items():
            if not isinstance(co_data, dict):
                continue
            for co_label, value in co_data.items():
                await override_svc.set(
                    project_id, year, scope,
                    f"comparison:{metric_key}:{year_str}:{co_label}",
                    "value", value, user_id
                )

    # 保存数据来源标注
    data_source_note = payload.get("data_source_note", "")
    await override_svc.set(
        project_id, year, scope, "data_source_note", "value",
        data_source_note, user_id
    )


def compute_eps_roe_values(inputs: dict) -> dict:
    """根据用户填写参数计算 EPS/ROE 指标。

    支持 CAS34 加权平均 ROE 和基本/稀释每股收益完整计算。
    """
    net_profit = inputs.get("net_profit")
    equity_end = inputs.get("equity_end")
    equity_begin = inputs.get("equity_begin")
    weighted_shares = inputs.get("weighted_avg_shares")
    preferred_dividend = inputs.get("preferred_dividend") or 0

    # 稀释因素
    convertible_bond_interest = inputs.get("convertible_bond_interest") or 0
    dilution_extra_shares = inputs.get("dilution_extra_shares") or 0

    # 归属于普通股股东的净利润
    p = None
    if net_profit is not None:
        p = float(net_profit) - float(preferred_dividend)

    # 加权平均净资产（CAS34: (期初+期末)/2，简化）
    avg_equity = None
    if equity_end is not None and equity_begin is not None:
        avg_equity = (float(equity_end) + float(equity_begin)) / 2
    elif equity_end is not None:
        avg_equity = float(equity_end)

    # 全面摊薄 ROE = P / 期末净资产
    roe_diluted = None
    if p is not None and equity_end not in (None, 0):
        roe_diluted = round(p / float(equity_end) * 100, 4)

    # 加权平均 ROE = P / 加权平均净资产
    roe_weighted = None
    if p is not None and avg_equity not in (None, 0):
        roe_weighted = round(p / avg_equity * 100, 4)

    # 基本每股收益 = P / 加权平均普通股数
    basic_eps = None
    if p is not None and weighted_shares not in (None, 0):
        basic_eps = round(p / float(weighted_shares), 4)

    # 稀释每股收益 = (P + 可转债税后利息) / (加权平均股数 + 稀释增加股数)
    diluted_eps = None
    diluted_numerator = (p or 0) + float(convertible_bond_interest)
    diluted_denominator = (float(weighted_shares) if weighted_shares else 0) + float(dilution_extra_shares)
    if diluted_numerator != 0 and diluted_denominator != 0 and p is not None:
        diluted_eps = round(diluted_numerator / diluted_denominator, 4)

    return {
        "roe_diluted": roe_diluted,
        "roe_weighted": roe_weighted,
        "basic_eps": basic_eps,
        "diluted_eps": diluted_eps,
    }


def compute_weighted_avg_shares(share_changes: list[dict]) -> float:
    """根据股本变动明细计算加权平均普通股数。

    加权平均股份数 = Σ(Si × Mi/12)
    其中 Si 是第 i 段的累计股份数，Mi 是该段的月份数(时间权重)。
    """
    if not share_changes:
        return 0
    total = 0.0
    for item in share_changes:
        shares = float(item.get("cum_shares") or item.get("shares") or 0)
        months = float(item.get("time_weight_months") or item.get("months") or 0)
        total += shares * months / 12.0
    return round(total, 2)


async def build_eps_roe(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
    year: int,
    *,
    net_profit: float | None = None,
    equity_end: float | None = None,
    equity_begin: float | None = None,
    share_capital: float | None = None,
) -> dict:
    """构建 EPS-ROE 计算表 sheet 结构（A1-14-7，含公式自动计算）。

    从 field_overrides 读取用户持久化的参数（股本变动/稀释因素/优先股股利等），
    合并报表自动取数后计算。
    """
    from app.services.field_override_service import FieldOverrideService

    scope = f"analytical_review:eps_roe:{project_id}"
    override_svc = FieldOverrideService(db)
    overrides = await override_svc.get_batch(project_id, year, scope)

    # 从 overrides 读取用户参数（覆盖自动取数值）
    params_override = overrides.get("params", {})
    preferred_dividend = params_override.get("preferred_dividend") or 0
    user_net_profit = params_override.get("net_profit")
    user_equity_end = params_override.get("equity_end")
    user_equity_begin = params_override.get("equity_begin")

    # 最终参数：用户覆盖 > 报表自动取数
    final_net_profit = user_net_profit if user_net_profit is not None else net_profit
    final_equity_end = user_equity_end if user_equity_end is not None else equity_end
    final_equity_begin = user_equity_begin if user_equity_begin is not None else equity_begin

    # 股本变动明细（从 overrides 读取）
    share_changes_data = overrides.get("share_changes", {})
    share_changes_json = share_changes_data.get("value")
    if share_changes_json and isinstance(share_changes_json, list):
        share_changes = share_changes_json
    else:
        # 默认：仅期初股份
        share_changes = [
            {
                "id": "s0",
                "date": "",
                "event_type": "期初股份",
                "shares_changed": 0,
                "cum_shares": share_capital or 0,
                "time_weight_months": 12,
            },
        ]

    # 从股本变动明细计算加权平均股数
    weighted_avg_shares = compute_weighted_avg_shares(share_changes)
    if weighted_avg_shares == 0 and share_capital:
        weighted_avg_shares = float(share_capital)

    # 稀释因素（从 overrides 读取）
    dilution_override = overrides.get("dilution_factors", {})
    convertible_bond_face_value = dilution_override.get("convertible_bond_face_value") or 0
    convertible_bond_rate = dilution_override.get("convertible_bond_rate") or 0
    convertible_bond_shares = dilution_override.get("convertible_bond_shares") or 0
    option_exercise_price = dilution_override.get("option_exercise_price") or 0
    option_shares = dilution_override.get("option_shares") or 0

    # 可转债税后利息 = 面值 × 利率 × (1 - 25%)（假设税率25%）
    convertible_bond_interest = float(convertible_bond_face_value) * float(convertible_bond_rate) / 100 * 0.75
    # 稀释增加股数 = 可转债转股数 + 期权增量股数
    dilution_extra_shares = float(convertible_bond_shares) + float(option_shares)

    inputs = {
        "net_profit": final_net_profit,
        "equity_end": final_equity_end,
        "equity_begin": final_equity_begin,
        "weighted_avg_shares": weighted_avg_shares,
        "preferred_dividend": preferred_dividend,
        "convertible_bond_interest": convertible_bond_interest,
        "dilution_extra_shares": dilution_extra_shares,
    }

    return {
        "title": "EPS-ROE计算表（参考）",
        "index": f"{wp_code}-7",
        "year": year,
        "inputs": {
            "net_profit": final_net_profit,
            "equity_end": final_equity_end,
            "equity_begin": final_equity_begin,
            "preferred_dividend": preferred_dividend,
            "weighted_avg_shares": weighted_avg_shares,
        },
        "share_changes": share_changes,
        "dilution_factors": {
            "convertible_bond_face_value": convertible_bond_face_value,
            "convertible_bond_rate": convertible_bond_rate,
            "convertible_bond_shares": convertible_bond_shares,
            "option_exercise_price": option_exercise_price,
            "option_shares": option_shares,
        },
        "computed": compute_eps_roe_values(inputs),
        "notes": [
            "净资产收益率（全面摊薄）= 归属于普通股股东的净利润 / 期末净资产",
            "净资产收益率（加权平均）= P / 加权平均净资产（CAS 34）",
            "基本每股收益 = (净利润 - 优先股股利) / 加权平均普通股股数",
            "稀释每股收益 = (净利润 - 优先股股利 + 可转债税后利息) / (加权平均股数 + 稀释增加股数)",
            "加权平均股数 = Σ(各段累计股份数 × 该段月份数 / 12)",
            "配股/公积金转增/拆股等股本变动按 CAS 34 规定调整加权平均股数",
        ],
    }


async def save_eps_roe(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    payload: dict,
    user_id: UUID | None = None,
) -> dict:
    """保存 EPS-ROE 用户参数并重新计算。

    payload 结构:
    {
      "params": {"net_profit": ..., "equity_end": ..., "equity_begin": ..., "preferred_dividend": ...},
      "share_changes": [{id, date, event_type, shares_changed, cum_shares, time_weight_months}],
      "dilution_factors": {convertible_bond_face_value, convertible_bond_rate, convertible_bond_shares, option_exercise_price, option_shares}
    }
    """
    from app.services.field_override_service import FieldOverrideService

    scope = f"analytical_review:eps_roe:{project_id}"
    override_svc = FieldOverrideService(db)

    # 保存用户参数
    params = payload.get("params", {})
    if params:
        for field, value in params.items():
            await override_svc.set(
                project_id, year, scope, "params", field, value, user_id
            )

    # 保存股本变动明细（整体作为 JSON list 存储）
    share_changes = payload.get("share_changes")
    if share_changes is not None:
        await override_svc.set(
            project_id, year, scope, "share_changes", "value", share_changes, user_id
        )

    # 保存稀释因素
    dilution_factors = payload.get("dilution_factors", {})
    if dilution_factors:
        for field, value in dilution_factors.items():
            await override_svc.set(
                project_id, year, scope, "dilution_factors", field, value, user_id
            )

    # 重新计算并返回
    weighted_avg_shares = compute_weighted_avg_shares(share_changes or [])
    convertible_bond_face_value = dilution_factors.get("convertible_bond_face_value") or 0
    convertible_bond_rate = dilution_factors.get("convertible_bond_rate") or 0
    convertible_bond_shares = dilution_factors.get("convertible_bond_shares") or 0
    option_shares = dilution_factors.get("option_shares") or 0
    convertible_bond_interest = float(convertible_bond_face_value) * float(convertible_bond_rate) / 100 * 0.75
    dilution_extra_shares = float(convertible_bond_shares) + float(option_shares)

    inputs = {
        "net_profit": params.get("net_profit"),
        "equity_end": params.get("equity_end"),
        "equity_begin": params.get("equity_begin"),
        "weighted_avg_shares": weighted_avg_shares,
        "preferred_dividend": params.get("preferred_dividend") or 0,
        "convertible_bond_interest": convertible_bond_interest,
        "dilution_extra_shares": dilution_extra_shares,
    }
    return compute_eps_roe_values(inputs)


# ---------------------------------------------------------------------------
# 内部取数辅助
# ---------------------------------------------------------------------------
async def _get_materiality(db: AsyncSession, project_id: UUID, year: int) -> Decimal:
    """从 materiality 表获取整体重要性水平。"""
    stmt = (
        sa.select(Materiality.overall_materiality)
        .where(
            Materiality.project_id == project_id,
            Materiality.year == year,
            Materiality.is_deleted == sa.false(),
        )
        .order_by(Materiality.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    val = result.scalar_one_or_none()
    return val if val is not None else Decimal("0")


async def _get_report_rows(
    db: AsyncSession, project_id: UUID, year: int, report_type: FinancialReportType
) -> dict[str, dict]:
    """从 financial_report 取某年某报表类型的所有行数据。

    Returns:
        dict[row_code -> {row_name, amount, indent_level, is_total_row}]
    """
    stmt = (
        sa.select(
            FinancialReport.row_code,
            FinancialReport.row_name,
            FinancialReport.current_period_amount,
            FinancialReport.indent_level,
            FinancialReport.is_total_row,
        )
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == report_type,
            FinancialReport.is_deleted == sa.false(),
        )
    )
    result = await db.execute(stmt)
    rows = {}
    for r in result.fetchall():
        rows[r.row_code] = {
            "row_name": r.row_name,
            "amount": r.current_period_amount or Decimal("0"),
            "indent_level": r.indent_level,
            "is_total_row": r.is_total_row,
        }
    return rows


async def _get_report_rows_batch(
    db: AsyncSession, project_id: UUID, years: list[int]
) -> dict[tuple[int, FinancialReportType], dict[str, dict]]:
    """一次查询获取多年度所有报表类型的数据（减少 DB 往返）。

    Returns:
        dict[(year, report_type) -> {row_code -> {row_name, amount, ...}}]
    """
    stmt = (
        sa.select(
            FinancialReport.year,
            FinancialReport.report_type,
            FinancialReport.row_code,
            FinancialReport.row_name,
            FinancialReport.current_period_amount,
            FinancialReport.indent_level,
            FinancialReport.is_total_row,
        )
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year.in_(years),
            FinancialReport.is_deleted == sa.false(),
        )
    )
    result = await db.execute(stmt)
    data: dict[tuple[int, FinancialReportType], dict[str, dict]] = {}
    for r in result.fetchall():
        key = (r.year, r.report_type)
        if key not in data:
            data[key] = {}
        data[key][r.row_code] = {
            "row_name": r.row_name,
            "amount": r.current_period_amount or Decimal("0"),
            "indent_level": r.indent_level,
            "is_total_row": r.is_total_row,
        }
    return data


async def _get_report_config_rows(
    db: AsyncSession, report_type: FinancialReportType, applicable_standard: str
) -> list[dict]:
    """从 report_config 获取报表行次结构（用于行遍历顺序和名称）。"""
    rc = ReportConfig.__table__
    stmt = (
        sa.select(rc.c.row_code, rc.c.row_name, rc.c.row_number, rc.c.indent_level, rc.c.is_total_row)
        .where(
            rc.c.report_type == report_type,
            rc.c.applicable_standard == applicable_standard,
            rc.c.is_deleted == sa.false(),
        )
        .order_by(rc.c.row_number)
    )
    result = await db.execute(stmt)
    return [
        {
            "row_code": r.row_code,
            "row_name": r.row_name,
            "row_number": r.row_number,
            "indent_level": r.indent_level,
            "is_total_row": r.is_total_row,
        }
        for r in result.fetchall()
    ]


# ---------------------------------------------------------------------------
# BS/IS 合计行 row_code 定义（用于纵向比重%计算基数）
# ---------------------------------------------------------------------------
BS_TOTAL_ASSET_CODE = "BS-039"       # 资产合计
BS_TOTAL_LIABILITY_EQUITY_CODE = "BS-099"  # 负债和股东权益合计
BS_EQUITY_TOTAL_CODE = "BS-098"      # 所有者权益合计
BS_SHARE_CAPITAL_CODE = "BS-078"     # 实收资本(股本)
IS_REVENUE_CODE = "IS-001"           # 营业收入
IS_NET_PROFIT_CODE = "IS-027"        # 净利润

# 同行业对比指标
_INDUSTRY_FINANCIAL_METRICS = [
    ("total_assets", "资产总额"),
    ("net_assets", "净资产额"),
    ("revenue", "营业收入"),
    ("net_profit", "净利润"),
    ("roe", "净资产收益率"),
    ("inventory_turnover", "存货周转率"),
    ("debt_ratio", "资产负债率"),
]
_INDUSTRY_COMPARISON_METRICS = [
    ("roe", "净资产收益率"),
    ("gross_margin", "综合毛利率"),
    ("segment_gross_margin", "XX毛利率"),
    ("receivable_turnover", "应收账款周转率"),
    ("inventory_turnover", "存货周转率"),
]
_COMPANY_LABELS = ["self", "A", "B", "C", "D", "E"]


# ---------------------------------------------------------------------------
# 核心数据组装函数
# ---------------------------------------------------------------------------
def _build_horizontal_rows(
    config_rows: list[dict],
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
    materiality: Decimal,
) -> list[dict]:
    """构建横向趋势分析行数据。"""
    rows = []
    for cfg in config_rows:
        rc = cfg["row_code"]
        name = cfg["row_name"]
        cur_info = current_data.get(rc, {})
        pri_info = prior_data.get(rc, {})
        current_amt = cur_info.get("amount", Decimal("0"))
        prior_amt = pri_info.get("amount", Decimal("0"))
        # 使用 financial_report 的 row_name，fallback 到 report_config
        display_name = cur_info.get("row_name") or pri_info.get("row_name") or name

        change, change_pct = compute_change(current_amt, prior_amt)
        status = classify_change(change_pct, change, materiality)

        rows.append({
            "row_code": rc,
            "name": display_name,
            "row_number": cfg["row_number"],
            "indent_level": cfg.get("indent_level", 0),
            "is_total_row": cfg.get("is_total_row", False),
            "prior": float(prior_amt),
            "current": float(current_amt),
            "change": float(change),
            "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
            "status": status,
            "reason": None,  # 预留变动原因
        })
    return rows


def _build_vertical_rows(
    config_rows: list[dict],
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
    current_total: Decimal,
    prior_total: Decimal,
    materiality: Decimal,
) -> list[dict]:
    """构建纵向结构分析行数据。"""
    rows = []
    for cfg in config_rows:
        rc = cfg["row_code"]
        name = cfg["row_name"]
        cur_info = current_data.get(rc, {})
        pri_info = prior_data.get(rc, {})
        current_amt = cur_info.get("amount", Decimal("0"))
        prior_amt = pri_info.get("amount", Decimal("0"))
        display_name = cur_info.get("row_name") or pri_info.get("row_name") or name

        cur_weight = compute_weight_pct(current_amt, current_total)
        pri_weight = compute_weight_pct(prior_amt, prior_total)

        # 比重%变动
        weight_change: float | None = None
        if cur_weight is not None and pri_weight is not None:
            weight_change = round(float(cur_weight - pri_weight), 2)

        change, change_pct = compute_change(current_amt, prior_amt)
        status = classify_change(change_pct, change, materiality)

        rows.append({
            "row_code": rc,
            "name": display_name,
            "row_number": cfg["row_number"],
            "indent_level": cfg.get("indent_level", 0),
            "is_total_row": cfg.get("is_total_row", False),
            "prior": float(prior_amt),
            "prior_weight_pct": round(float(pri_weight), 2) if pri_weight is not None else None,
            "current": float(current_amt),
            "current_weight_pct": round(float(cur_weight), 2) if cur_weight is not None else None,
            "weight_change_pct": weight_change,
            "status": status,
            "reason": None,
        })
    return rows


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def get_analytical_review_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str = "A1-13",
    scope: str = "standalone",
) -> dict:
    """生成分析性复核全量数据。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        year: 审计年度
        wp_code: 底稿编号 ("A1-13" 或 "A1-14")
        scope: 报表范围 ("standalone" 或 "consolidated")

    Returns:
        包含 bs_horizontal/bs_vertical/is_horizontal/is_vertical 等 sheet 数据的字典
    """
    # 1. 获取重要性水平
    materiality = await _get_materiality(db, project_id, year)

    # 2. 确定 applicable_standard（与报表模块一致）
    applicable_standard = f"soe_{scope}"

    # 3. 获取报表行次结构
    bs_config = await _get_report_config_rows(
        db, FinancialReportType.balance_sheet, applicable_standard
    )
    is_config = await _get_report_config_rows(
        db, FinancialReportType.income_statement, applicable_standard
    )

    # 4. 获取本年/上年 financial_report 数据（合并为单次查询，减少 DB 往返）
    all_report_data = await _get_report_rows_batch(db, project_id, [year, year - 1])
    bs_current = all_report_data.get((year, FinancialReportType.balance_sheet), {})
    bs_prior = all_report_data.get((year - 1, FinancialReportType.balance_sheet), {})
    is_current = all_report_data.get((year, FinancialReportType.income_statement), {})
    is_prior = all_report_data.get((year - 1, FinancialReportType.income_statement), {})

    # 5. 确定纵向分析基数（合计行金额）
    bs_cur_total_asset = bs_current.get(BS_TOTAL_ASSET_CODE, {}).get("amount", Decimal("0"))
    bs_pri_total_asset = bs_prior.get(BS_TOTAL_ASSET_CODE, {}).get("amount", Decimal("0"))
    bs_cur_total_le = bs_current.get(BS_TOTAL_LIABILITY_EQUITY_CODE, {}).get("amount", Decimal("0"))
    bs_pri_total_le = bs_prior.get(BS_TOTAL_LIABILITY_EQUITY_CODE, {}).get("amount", Decimal("0"))
    is_cur_revenue = is_current.get(IS_REVENUE_CODE, {}).get("amount", Decimal("0"))
    is_pri_revenue = is_prior.get(IS_REVENUE_CODE, {}).get("amount", Decimal("0"))

    # 6. 组装各 sheet

    # --- BS 横向 ---
    scope_label = "母公司" if scope == "standalone" else "合并"
    bs_horizontal = {
        "title": f"已审资产负债表（{scope_label}）横向趋势分析",
        "index": f"{wp_code}-1",
        "columns": ["项目", "行次", "上年审定数", "本年审定数", "变动额", "变动%", "变动状况", "显著变动原因分析"],
        "rows": _build_horizontal_rows(bs_config, bs_current, bs_prior, materiality),
    }

    # --- BS 纵向 ---
    # 资产类用资产合计作基数，负债/权益类用负债+权益合计作基数
    # 简化处理：统一用资产合计（资产=负债+权益）
    bs_vertical = {
        "title": f"已审资产负债表（{scope_label}）纵向结构分析",
        "index": f"{wp_code}-2",
        "columns": ["项目", "行次", "上年审定数", "比重%", "本年审定数", "比重%", "本年比上年增长差异", "变动状况", "显著变动原因分析"],
        "rows": _build_vertical_rows(
            bs_config, bs_current, bs_prior,
            bs_cur_total_asset, bs_pri_total_asset, materiality
        ),
    }

    # --- IS 横向 ---
    is_horizontal = {
        "title": f"已审利润表（{scope_label}）横向趋势分析",
        "index": f"{wp_code}-3",
        "columns": ["项目", "行次", "上年审定数", "本年审定数", "变动额", "变动%", "变动状况", "显著变动原因分析"],
        "rows": _build_horizontal_rows(is_config, is_current, is_prior, materiality),
    }

    # --- IS 纵向 ---
    is_vertical = {
        "title": f"已审利润表（{scope_label}）纵向结构分析",
        "index": f"{wp_code}-4",
        "columns": ["项目", "行次", "上年审定数", "比重%", "本年审定数", "比重%", "本年比上年增长差异", "变动状况", "显著变动原因分析"],
        "rows": _build_vertical_rows(
            is_config, is_current, is_prior,
            is_cur_revenue, is_pri_revenue, materiality
        ),
    }

    # 7. 比率分析
    from app.services.ratio_analysis_engine import get_ratio_analysis_data

    try:
        ratio_analysis = await get_ratio_analysis_data(db, project_id, year, wp_code)
    except Exception:
        logger.exception("比率分析计算失败，返回 None")
        ratio_analysis = None

    # 8. 上市公司专用 sheet（A1-14 + is_listed）
    industry_comparison = None
    eps_roe = None
    is_listed = await _get_is_listed(db, project_id) if wp_code == "A1-14" else False
    if wp_code == "A1-14" and is_listed:
        industry_comparison = await build_industry_comparison(db, project_id, wp_code, year)
        cur_np = is_current.get(IS_NET_PROFIT_CODE, {}).get("amount")
        cur_equity = bs_current.get(BS_EQUITY_TOTAL_CODE, {}).get("amount")
        pri_equity = bs_prior.get(BS_EQUITY_TOTAL_CODE, {}).get("amount")
        share_capital = bs_current.get(BS_SHARE_CAPITAL_CODE, {}).get("amount")
        eps_roe = await build_eps_roe(
            db,
            project_id,
            wp_code,
            year,
            net_profit=float(cur_np) if cur_np is not None else None,
            equity_end=float(cur_equity) if cur_equity is not None else None,
            equity_begin=float(pri_equity) if pri_equity is not None else None,
            share_capital=float(share_capital) if share_capital is not None else None,
        )

    return {
        "wp_code": wp_code,
        "scope": scope,
        "year": year,
        "materiality": float(materiality),
        "is_listed": is_listed,
        "sheets": {
            "bs_horizontal": bs_horizontal,
            "bs_vertical": bs_vertical,
            "is_horizontal": is_horizontal,
            "is_vertical": is_vertical,
            "ratio_analysis": ratio_analysis,
            "industry_comparison": industry_comparison,
            "eps_roe": eps_roe,
        },
    }
