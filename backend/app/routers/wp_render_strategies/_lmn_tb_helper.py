"""L/M/N 循环审定表 TB 取数共享 helper.

统一从四表库查询科目余额/发生额，供各 render 策略调用。
灰度开关 LMN_FOUR_TABLE_EXTRACTION_ENABLED 控制（默认 False=返回全 0）。

**改造要点（L 类四表取数 spec）**

1. **叶子判定委托共享件**：原 `_is_leaf` 用 ``other.startswith(code)`` 判定，**缺点号
   边界** —— 前缀 ``2231`` 会把 ``22310x``（不同科目）误判成其子科目。已改为委托
   ``four_table.leaf_aggregation.select_leaves``（F1/G7 已删过同款自造实现）。

2. **入参改科目码集合**：报表行公式可能解析出多个标准码，硬编码单个字符串无法承载。
   兼容单字符串入参（既有调用方与测试零回归）。

3. **🔴 损益类删 ``debit - credit``**：含年末结转损益的全年账上，``6603`` 及**每一个**
   子科目都满足 ``debit == credit``（DB 实证 543,020,073.49 双侧完全相等）→ 差额恒 0，
   L8 财务费用取数从未产出过非零值。``tb_ledger`` 路径同病（且跨项目聚合出 366 亿的
   垃圾数）。平台权威口径 = ``trial_balance``（`recalc` 已按发生额写好，``TB()`` 读的
   就是它；``report_config`` ``IS-007/IS-025 = TB('6603','本期发生额')``），实证同一
   科目 ``trial_balance`` 有正确值 171,005,147.56；兜底取 ``tb_balance.debit_amount``
   （**仅借方**，负借方语义即贷方性质，直取可保留符号）。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.3, 2.4, 2.5, 10.2 / Property 3, 4
"""

import logging
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from app.core.config import settings
from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table.leaf_aggregation import (
    LeafRow,
    filter_by_prefixes,
    select_leaves,
    to_leaf_rows,
)

from ._context import RenderContext

logger = logging.getLogger(__name__)

#: 灰度关闭时返回的零值结果
_ZERO_RESULT: dict[str, Any] = {
    "account_code": "",
    "begin_balance": 0,
    "end_balance": 0,
    "debit_amount": 0,
    "credit_amount": 0,
}

#: 损益类取数来源标记（溯源展示）
SOURCE_TRIAL_BALANCE = "trial_balance"
SOURCE_TB_BALANCE_DEBIT = "tb_balance_debit"
SOURCE_NONE = "none"


def _as_codes(account_code: str | Sequence[str]) -> list[str]:
    """入参归一为科目码列表（兼容既有单字符串调用方）。"""
    if isinstance(account_code, str):
        raw: Sequence[str] = [account_code]
    else:
        raw = account_code or []
    return [str(c or "").strip() for c in raw if str(c or "").strip()]


def _display_code(codes: list[str]) -> str:
    """溯源展示用的科目码字面（多码用 ``/`` 连接，保持单码时与改造前一致）。"""
    return "/".join(codes)


async def _fetch_tb_balance_rows(
    ctx: RenderContext, codes: list[str]
) -> list[LeafRow]:
    """取该项目 active 数据集下、命中任一码前缀的 `tb_balance` 行（含父与子）。"""
    if not codes:
        return []
    active_filter = await get_active_filter(
        ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
    )
    stmt = sa.select(
        TbBalance.account_code,
        TbBalance.account_name,
        TbBalance.opening_balance,
        TbBalance.closing_balance,
        TbBalance.debit_amount,
        TbBalance.credit_amount,
        TbBalance.closing_direction,
        TbBalance.dataset_id,
    ).where(
        TbBalance.project_id == str(ctx.project_id),
        sa.or_(*[TbBalance.account_code.like(f"{c}%") for c in codes]),
        active_filter,
    )
    return to_leaf_rows((await ctx.db.execute(stmt)).fetchall())


async def fetch_tb_for_balance(
    ctx: RenderContext, account_code: str | Sequence[str]
) -> dict[str, Any]:
    """负债/权益/资产类科目：取期初余额 + 期末余额.

    精确码优先；无精确码时**叶子**聚合（防父子双算）。叶子判定带点号边界。
    灰度关闭返回全 0。fail-open 不阻断 render。

    Args:
        ctx: `RenderContext`。
        account_code: 科目码或科目码集合（标准码/原始码前缀均可）。

    Returns:
        ``{"account_code","begin_balance","end_balance","debit_amount","credit_amount"}``。
    """
    codes = _as_codes(account_code)
    display = _display_code(codes)

    if not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return {**_ZERO_RESULT, "account_code": display}

    result: dict[str, Any] = {
        "account_code": display,
        "begin_balance": 0,
        "end_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
    }
    if not codes:
        return result

    try:
        rows = await _fetch_tb_balance_rows(ctx, codes)
        if not rows:
            return result

        # ① 精确码命中（父科目行本身就有金额）→ 直接用，不再下钻
        exact = [r for r in rows if r.account_code in set(codes)]
        if exact:
            result["begin_balance"] = sum(r.opening for r in exact)
            result["end_balance"] = sum(r.closing for r in exact)
            result["debit_amount"] = sum(r.debit for r in exact)
            result["credit_amount"] = sum(r.credit for r in exact)
            return result

        # ② 叶子聚合（点号边界，委托共享件）
        leaves = filter_by_prefixes(select_leaves(rows), codes)
        result["begin_balance"] = sum(r.opening for r in leaves)
        result["end_balance"] = sum(r.closing for r in leaves)
        result["debit_amount"] = sum(r.debit for r in leaves)
        result["credit_amount"] = sum(r.credit for r in leaves)

    except Exception as e:  # noqa: BLE001
        logger.warning("LMN TB helper fetch_tb_for_balance(%s) failed: %s", display, e)

    return result


async def fetch_tb_for_income(
    ctx: RenderContext, account_code: str | Sequence[str]
) -> dict[str, Any]:
    """损益类科目：取**本期发生额**（`trial_balance` 权威口径优先）。

    🔴 **不再使用 ``debit - credit``** —— 含年末结转损益的账套上该差额结构性恒为 0
    （见模块 docstring 的 DB 实证）。取数优先级：

    1. ``trial_balance.unadjusted_amount``（`recalc` 已按发生额写好，即 ``TB()`` 口径）
    2. ``tb_balance.debit_amount`` 叶子求和（**仅借方**，保留符号）

    ``end_balance`` 沿用旧键名承载本期发生额（前端已在读该键，不改契约）。
    另增 ``occurrence`` 同值别名与 ``source`` 溯源标记。

    灰度关闭返回全 0。fail-open 不阻断 render。
    """
    codes = _as_codes(account_code)
    display = _display_code(codes)

    if not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return {**_ZERO_RESULT, "account_code": display}

    result: dict[str, Any] = {
        "account_code": display,
        "begin_balance": 0,
        "end_balance": 0,  # 承载本期发生额（旧键名，前端已在读）
        "debit_amount": 0,
        "credit_amount": 0,
        "occurrence": 0,
        "source": SOURCE_NONE,
    }
    if not codes:
        return result

    # ① trial_balance 权威口径（精确标准码，不用前缀 —— 父子并存会双算）
    try:
        tb_filter = await get_active_filter(
            ctx.db, TrialBalance.__table__, ctx.project_id, ctx.year or 0
        )
        stmt = sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.unadjusted_amount,
            TrialBalance.opening_balance,
        ).where(
            TrialBalance.project_id == ctx.project_id,
            TrialBalance.standard_account_code.in_(codes),
            tb_filter,
        )
        rows = (await ctx.db.execute(stmt)).fetchall()
        if rows:
            occurrence = sum(float(r.unadjusted_amount or 0) for r in rows)
            result["begin_balance"] = sum(float(r.opening_balance or 0) for r in rows)
            result["end_balance"] = occurrence
            result["occurrence"] = occurrence
            result["debit_amount"] = occurrence
            result["source"] = SOURCE_TRIAL_BALANCE
            return result
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "LMN TB helper fetch_tb_for_income(%s) trial_balance failed: %s", display, e
        )

    # ② tb_balance 叶子借方兜底
    try:
        rows = await _fetch_tb_balance_rows(ctx, codes)
        if not rows:
            return result
        exact = [r for r in rows if r.account_code in set(codes)]
        picked = exact or filter_by_prefixes(select_leaves(rows), codes)
        occurrence = sum(r.debit for r in picked)
        result["begin_balance"] = sum(r.opening for r in picked)
        result["end_balance"] = occurrence
        result["occurrence"] = occurrence
        result["debit_amount"] = occurrence
        result["credit_amount"] = sum(r.credit for r in picked)
        result["source"] = SOURCE_TB_BALANCE_DEBIT
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "LMN TB helper fetch_tb_for_income(%s) tb_balance failed: %s", display, e
        )

    return result


async def fetch_leaf_rows(
    ctx: RenderContext, account_code: str | Sequence[str]
) -> list[LeafRow]:
    """取叶子行明细（供 `adjudication_prefill` 分类聚合与勾稽自检）。

    灰度关闭返回 ``[]``。fail-open 返回 ``[]``。
    """
    codes = _as_codes(account_code)
    if not codes or not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return []
    try:
        rows = await _fetch_tb_balance_rows(ctx, codes)
        return filter_by_prefixes(select_leaves(rows), codes)
    except Exception as e:  # noqa: BLE001
        logger.warning("LMN TB helper fetch_leaf_rows(%s) failed: %s", codes, e)
        return []


async def fetch_parent_rows(
    ctx: RenderContext, account_code: str | Sequence[str]
) -> list[LeafRow]:
    """取父科目行本身（供「叶子和 == 父额」勾稽自检）。灰度关闭返回 ``[]``。"""
    codes = _as_codes(account_code)
    if not codes or not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return []
    try:
        rows = await _fetch_tb_balance_rows(ctx, codes)
        wanted = set(codes)
        return [r for r in rows if r.account_code in wanted]
    except Exception as e:  # noqa: BLE001
        logger.warning("LMN TB helper fetch_parent_rows(%s) failed: %s", codes, e)
        return []


__all__ = [
    "SOURCE_NONE",
    "SOURCE_TB_BALANCE_DEBIT",
    "SOURCE_TRIAL_BALANCE",
    "fetch_leaf_rows",
    "fetch_parent_rows",
    "fetch_tb_for_balance",
    "fetch_tb_for_income",
]
