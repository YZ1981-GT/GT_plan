"""L/M/N 循环审定表 TB 取数共享 helper.

统一从 tb_balance 查询科目余额/发生额，供各 render 策略调用。
灰度开关 LMN_FOUR_TABLE_EXTRACTION_ENABLED 控制（默认 False=返回全 0）。
"""

import logging
from typing import Any

import sqlalchemy as sa

from app.core.config import settings
from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 灰度关闭时返回的零值结果
_ZERO_RESULT: dict[str, Any] = {
    "account_code": "",
    "begin_balance": 0,
    "end_balance": 0,
    "debit_amount": 0,
    "credit_amount": 0,
}


def _is_leaf(code: str, all_codes: list[str]) -> bool:
    """判断 code 是否为叶子科目（不是任何其它 code 的前缀）."""
    for other in all_codes:
        if other != code and other.startswith(code):
            return False
    return True


async def fetch_tb_for_balance(ctx: RenderContext, account_code: str) -> dict[str, Any]:
    """负债/权益/资产类科目：取期初余额 + 期末余额.

    精确码优先 able 无精确码时叶子聚合（防父子双算）。
    灰度关闭返回全 0。fail-open 不阻断 render。
    """
    if not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return {**_ZERO_RESULT, "account_code": account_code}

    result: dict[str, Any] = {
        "account_code": account_code,
        "begin_balance": 0,
        "end_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
    }

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )

        # ① 精确码查询
        exact_stmt = sa.select(
            TbBalance.opening_balance.label("begin_balance"),
            TbBalance.closing_balance.label("end_balance"),
            TbBalance.debit_amount,
            TbBalance.credit_amount,
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code == account_code,
            active_filter,
        )
        rows = (await ctx.db.execute(exact_stmt)).fetchall()

        if rows:
            # 精确码命中（可能多行=多 dataset 残留，取首行）
            row = rows[0]
            result["begin_balance"] = float(row.begin_balance or 0)
            result["end_balance"] = float(row.end_balance or 0)
            result["debit_amount"] = float(row.debit_amount or 0)
            result["credit_amount"] = float(row.credit_amount or 0)
            return result

        # ② 前缀 LIKE 叶子聚合
        prefix_stmt = sa.select(
            TbBalance.account_code,
            TbBalance.opening_balance.label("begin_balance"),
            TbBalance.closing_balance.label("end_balance"),
            TbBalance.debit_amount,
            TbBalance.credit_amount,
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code.like(f"{account_code}%"),
            active_filter,
        )
        all_rows = (await ctx.db.execute(prefix_stmt)).fetchall()

        if all_rows:
            all_codes = [r.account_code for r in all_rows]
            begin_sum = 0.0
            end_sum = 0.0
            debit_sum = 0.0
            credit_sum = 0.0
            for r in all_rows:
                if _is_leaf(r.account_code, all_codes):
                    begin_sum += float(r.begin_balance or 0)
                    end_sum += float(r.end_balance or 0)
                    debit_sum += float(r.debit_amount or 0)
                    credit_sum += float(r.credit_amount or 0)
            result["begin_balance"] = begin_sum
            result["end_balance"] = end_sum
            result["debit_amount"] = debit_sum
            result["credit_amount"] = credit_sum

    except Exception as e:  # noqa: BLE001
        logger.warning("LMN TB helper fetch_tb_for_balance(%s) failed: %s", account_code, e)

    return result


async def fetch_tb_for_income(ctx: RenderContext, account_code: str) -> dict[str, Any]:
    """损益借方类科目：取借方发生额 - 贷方发生额 = 净发生额.

    end_balance 存储净发生额（借-贷），方便前端统一消费。
    灰度关闭返回全 0。fail-open 不阻断 render。
    """
    if not getattr(settings, "LMN_FOUR_TABLE_EXTRACTION_ENABLED", False):
        return {**_ZERO_RESULT, "account_code": account_code}

    result: dict[str, Any] = {
        "account_code": account_code,
        "begin_balance": 0,
        "end_balance": 0,  # 存净发生额
        "debit_amount": 0,
        "credit_amount": 0,
    }

    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )

        # ① 精确码
        exact_stmt = sa.select(
            TbBalance.debit_amount,
            TbBalance.credit_amount,
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code == account_code,
            active_filter,
        )
        rows = (await ctx.db.execute(exact_stmt)).fetchall()

        if rows:
            row = rows[0]
            debit = float(row.debit_amount or 0)
            credit = float(row.credit_amount or 0)
            result["debit_amount"] = debit
            result["credit_amount"] = credit
            result["end_balance"] = debit - credit
            return result

        # ② 前缀叶子聚合
        prefix_stmt = sa.select(
            TbBalance.account_code,
            TbBalance.debit_amount,
            TbBalance.credit_amount,
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code.like(f"{account_code}%"),
            active_filter,
        )
        all_rows = (await ctx.db.execute(prefix_stmt)).fetchall()

        if all_rows:
            all_codes = [r.account_code for r in all_rows]
            debit_sum = 0.0
            credit_sum = 0.0
            for r in all_rows:
                if _is_leaf(r.account_code, all_codes):
                    debit_sum += float(r.debit_amount or 0)
                    credit_sum += float(r.credit_amount or 0)
            result["debit_amount"] = debit_sum
            result["credit_amount"] = credit_sum
            result["end_balance"] = debit_sum - credit_sum

    except Exception as e:  # noqa: BLE001
        logger.warning("LMN TB helper fetch_tb_for_income(%s) failed: %s", account_code, e)

    return result
