"""自定义底稿公式表达式求值（custom-workpaper-formula-binding 补强）。

将 wp_formula.expression 求值为 Decimal，供写回 parsed_data 目标单元格展示。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.formula_engine import FormulaContext, execute
from app.services.formula_engine import WPExecutor

logger = logging.getLogger(__name__)

_TB_PATTERN = re.compile(r"TB\('([^']+)','([^']+)'\)")
_SUM_TB_PATTERN = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
# 三参 WP（D2-3 嵌套寻址）须先于两参匹配：WP('D2','坏账准备明细表D2-3','本期计提合计')
_WP3_PATTERN = re.compile(r"WP\('([^']+)','([^']+)','([^']+)'\)")
_WP_PATTERN = re.compile(r"WP\('([^']+)','([^']+)'\)")

_COLUMN_MAP = {
    "期末余额": "audited_amount",
    "审定数": "audited_amount",
    "年初余额": "opening_balance",
    "期初余额": "opening_balance",
    "未审数": "unadjusted_amount",
    "RJE调整": "rje_adjustment",
    "AJE调整": "aje_adjustment",
}


async def _resolve_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
    column_name: str,
) -> Decimal:
    field = _COLUMN_MAP.get(column_name, "audited_amount")
    row = (
        await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return Decimal("0")
    val = getattr(row, field, None)
    if field == "_period_amount":
        amount = row.unadjusted_amount or Decimal("0")
        opening = row.opening_balance or Decimal("0")
        return amount - opening
    return val if val is not None else Decimal("0")


async def _resolve_sum_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    code_range: str,
    column_name: str,
) -> Decimal:
    parts = code_range.split("~")
    if len(parts) != 2:
        return Decimal("0")
    start_code, end_code = parts[0].strip(), parts[1].strip()
    field = _COLUMN_MAP.get(column_name, "audited_amount")
    rows = (
        await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
    ).scalars().all()
    total = Decimal("0")
    for row in rows:
        val = getattr(row, field, None)
        total += val if val is not None else Decimal("0")
    return total


async def evaluate_wp_formula_expression(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    expression: str,
) -> tuple[Decimal, list[str]]:
    """求值自定义底稿公式表达式。

    支持：字面量、TB/SUM_TB、WP（含单元格地址 B5）、四则运算与内置函数（委托 L1 execute）。
    失败返回 (Decimal('0'), errors)。
    """
    errors: list[str] = []
    raw = (expression or "").strip()
    if not raw:
        return Decimal("0"), errors
    if raw.startswith("="):
        raw = raw[1:].strip()

    # 纯数字字面量
    try:
        return Decimal(raw.replace(",", "")), errors
    except (InvalidOperation, ValueError):
        pass

    expr = raw
    # 三参 WP（D2-3 嵌套寻址）先处理，避免被两参正则截断
    for match in _WP3_PATTERN.finditer(raw):
        wp_code, sheet_name, field = match.group(1), match.group(2), match.group(3)
        try:
            val = await WPExecutor.execute(
                db, project_id, wp_code, sheet_name, field=field
            )
        except Exception as e:
            logger.warning("WP 三参求值失败 %s: %s", match.group(0), e)
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _WP_PATTERN.finditer(raw):
        # 跳过已被三参正则消费的片段（三参形态在 raw 中仍可被两参 finditer 命中前两参）
        if match.group(0) not in expr:
            continue
        wp_code, col = match.group(1), match.group(2)
        try:
            val = await WPExecutor.execute(db, project_id, wp_code, col)
        except Exception as e:
            logger.warning("WP 求值失败 %s: %s", match.group(0), e)
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _SUM_TB_PATTERN.finditer(raw):
        try:
            val = await _resolve_sum_tb(
                db, project_id, year, match.group(1), match.group(2)
            )
        except Exception as e:
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _TB_PATTERN.finditer(raw):
        try:
            val = await _resolve_tb(
                db, project_id, year, match.group(1), match.group(2)
            )
        except Exception as e:
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    ctx = FormulaContext(tb_data={}, row_cache={})
    result = execute(expr, ctx)
    errors.extend(result.errors)
    return result.value, errors
