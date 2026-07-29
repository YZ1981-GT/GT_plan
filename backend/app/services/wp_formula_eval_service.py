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
from app.services.dataset_query import get_active_filter
from app.services.formula_engine import FormulaContext, execute
from app.services.formula_engine import WPExecutor

logger = logging.getLogger(__name__)

_TB_PATTERN = re.compile(r"TB\('([^']+)','([^']+)'\)")
_SUM_TB_PATTERN = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
# 三参 WP（D2-3 嵌套寻址）须先于两参匹配：WP('D2','坏账准备明细表D2-3','本期计提合计')
_WP3_PATTERN = re.compile(r"WP\('([^']+)','([^']+)','([^']+)'\)")
_WP_PATTERN = re.compile(r"WP\('([^']+)','([^']+)'\)")

# ── d-cycle-four-table-extraction-formulas 决策3（方案 a）：Tier A 可编辑公式
# 不支持 AUX/PREV/序时账（LEDGER/COUNT_LEDGER）函数——这些正是 Tier B 复杂归集，
# 由 `_build_adjudication_prefill` prefill 承担。保存端点检出即返 422（不静默返 0）。
# 用 \b 词边界避免误伤：`COUNT_LEDGER(` 中 `LEDGER` 前是 `_`（词字符），故
# `\bLEDGER\(` 不会命中 COUNT_LEDGER，二者各自单列。
_UNSUPPORTED_FUNCTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AUX", re.compile(r"\bAUX\s*\(")),
    ("PREV", re.compile(r"\bPREV\s*\(")),
    ("LEDGER", re.compile(r"\bLEDGER\s*\(")),
    ("COUNT_LEDGER", re.compile(r"\bCOUNT_LEDGER\s*\(")),
)


def find_unsupported_formula_functions(expression: str | None) -> list[str]:
    """检出 Tier A 可编辑公式表达式中不受支持的四表库函数（决策3 方案 a）。

    返回命中的函数名列表（去重、保持声明顺序）。当前评估器
    ``evaluate_wp_formula_expression`` 只真实实现 ``TB``/``SUM_TB``/``WP``（+ 字面量/
    四则运算/``Sheet!Cell`` 跨 sheet 引用），``AUX``/``PREV``/``LEDGER``/``COUNT_LEDGER``
    未实现（会静默求值为 0），故保存时应拒绝而非静默落空。

    仅作纯字符串检测（不依赖 DB），供保存端点在写库前调用。
    """
    if not expression:
        return []
    raw = expression.strip()
    if raw.startswith("="):
        raw = raw[1:]
    hits: list[str] = []
    for name, pat in _UNSUPPORTED_FUNCTION_PATTERNS:
        if pat.search(raw) and name not in hits:
            hits.append(name)
    return hits

_COLUMN_MAP = {
    "期末余额": "audited_amount",
    "审定数": "audited_amount",
    "年初余额": "opening_balance",
    "期初余额": "opening_balance",
    "未审数": "unadjusted_amount",
    "RJE调整": "rje_adjustment",
    "AJE调整": "aje_adjustment",
    "借方发生额": "debit_amount",
    "贷方发生额": "credit_amount",
}


async def _resolve_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
    column_name: str,
) -> Decimal:
    field = _COLUMN_MAP.get(column_name, "audited_amount")
    # 数据集版本口径统一（与 Tier B prefill 同口径，见决策3）：
    # 用 get_active_filter 替代裸 is_deleted，规避读到 superseded/staged 数据。
    active_filter = await get_active_filter(
        db, TrialBalance.__table__, project_id, year
    )
    row = (
        await db.execute(
            sa.select(TrialBalance).where(
                active_filter,
                TrialBalance.standard_account_code == account_code,
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
    # 数据集版本口径统一（与 Tier B prefill 同口径，见决策3）。
    active_filter = await get_active_filter(
        db, TrialBalance.__table__, project_id, year
    )
    rows = (
        await db.execute(
            sa.select(TrialBalance).where(
                active_filter,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
            )
        )
    ).scalars().all()
    total = Decimal("0")
    for row in rows:
        val = getattr(row, field, None)
        total += val if val is not None else Decimal("0")
    return total


def _resolve_cross_sheet_refs(
    raw: str,
    parsed_data: dict | None,
    *,
    project_id: str | None = None,
    parent_wp_code: str | None = None,
) -> tuple[str, list[str]]:
    """将 ``=Sheet!Cell`` 跨 sheet 引用经 CrossSheetResolver 追溯解析为值后替换（Req 14.2）。

    复用 ``custom_query.cross_sheet_resolver.CrossSheetResolver``（BFS + 环检测 +
    ACNR addr_id 解析）追溯每个跨 sheet 引用链，取链首节点（目标单元）的值代入
    表达式；缺失/无法解析 → 代入 0 并记 warning（单条失败不阻断整体，Req 15.5 语义）。

    Returns:
        (substituted_expr, errors)。无 parsed_data 或无跨 sheet 引用时原样返回。
    """
    errors: list[str] = []
    if not parsed_data:
        return raw, errors

    # 延迟导入避免与 custom_query 包的循环依赖。
    from app.services.custom_query.cross_sheet_resolver import (
        CrossSheetResolver,
        _CROSS_SHEET_REF_PATTERN,
    )

    matches = list(_CROSS_SHEET_REF_PATTERN.finditer(raw))
    if not matches:
        return raw, errors

    resolver = CrossSheetResolver(
        project_id=project_id, parent_wp_code=parent_wp_code
    )
    expr = raw
    for match in matches:
        ref_text = match.group(0)
        ref_sheet = match.group(1) or match.group(2)
        ref_cell = match.group(3).upper()
        try:
            chain_resp = resolver.resolve(parsed_data, ref_sheet, ref_cell)
            node = chain_resp.chain[0] if chain_resp.chain else None
            raw_val = node.value if node is not None else None
            if raw_val is None:
                val = Decimal("0")
                errors.append(f"{ref_text}: 跨 sheet 引用目标缺失，代入 0")
            else:
                try:
                    val = Decimal(str(raw_val).replace(",", ""))
                except (InvalidOperation, ValueError):
                    val = Decimal("0")
                    errors.append(f"{ref_text}: 跨 sheet 引用值非数值，代入 0")
        except Exception as e:  # noqa: BLE001 — 单条失败不阻断整体求值
            logger.warning("跨 sheet 引用求值失败 %s: %s", ref_text, e)
            val = Decimal("0")
            errors.append(f"{ref_text}: {e}")
        expr = expr.replace(ref_text, str(val), 1)

    return expr, errors


async def evaluate_wp_formula_expression(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    expression: str,
    parsed_data: dict | None = None,
    parent_wp_code: str | None = None,
) -> tuple[Decimal, list[str]]:
    """求值自定义底稿公式表达式。

    支持：字面量、TB/SUM_TB、WP（含单元格地址 B5）、``Sheet!Cell`` 跨 sheet 引用
    （经 CrossSheetResolver 追溯，Req 14.2）、四则运算与内置函数（委托 L1 execute）。
    失败返回 (Decimal('0'), errors)。

    Args:
        parsed_data: 底稿 ``working_paper.parsed_data``（含 univer_snapshot），
            提供时启用 ``Sheet!Cell`` 跨 sheet 引用追溯求值。
        parent_wp_code: 父底稿码，供 CrossSheetResolver 构造 grammar_v1 3 参 WP。
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

    # 跨 sheet 引用（Sheet!Cell）先经 CrossSheetResolver 追溯解析为值代入（Req 14.2）
    raw, cross_errors = _resolve_cross_sheet_refs(
        raw,
        parsed_data,
        project_id=str(project_id) if project_id is not None else None,
        parent_wp_code=parent_wp_code,
    )
    errors.extend(cross_errors)

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
