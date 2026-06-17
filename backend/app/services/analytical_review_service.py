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
IS_REVENUE_CODE = "IS-001"           # 营业收入


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

    return {
        "wp_code": wp_code,
        "scope": scope,
        "year": year,
        "materiality": float(materiality),
        "sheets": {
            "bs_horizontal": bs_horizontal,
            "bs_vertical": bs_vertical,
            "is_horizontal": is_horizontal,
            "is_vertical": is_vertical,
            "ratio_analysis": ratio_analysis,
            "industry_comparison": None,  # P1
            "eps_roe": None,  # P1
        },
    }
