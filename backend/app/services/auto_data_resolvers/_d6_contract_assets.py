"""D6 合同资产 Auto Data Resolvers.

2个resolver:
- d6_tb_unadjusted: trial_balance 科目1141 期初/期末未审数
- d6_impairment_tb: trial_balance 坏账准备相关科目（1141对应减值）期初/期末未审数

科目依据：合同资产科目为 1141（标准科目表 direction=debit）；`report_config` 报表行
BS-011 四准则一致 `TB('1141','期末余额')`。原 `1402` 是在途物资（存货类），属误用。

Usage:
    result = await resolve_auto_data_source(db, project_id, year, "d6_tb_unadjusted")
    result = await resolve_auto_data_source(db, project_id, year, "d6_impairment_tb")
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver: d6_tb_unadjusted — 科目1141期初/期末未审数
# ═══════════════════════════════════════════════════════════════════════════════


@auto_resolver("d6_tb_unadjusted")
async def _resolve_d6_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取科目1141的本期/上期未审数。

    Returns:
        {
            "summary": str,
            "prior_unadjusted": float,
            "current_unadjusted": float,
        }
    """
    result_data: dict[str, Any] = {
        "prior_unadjusted": 0.0,
        "current_unadjusted": 0.0,
    }

    # 本期未审数
    current = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '1141'
        """),
        {"pid": str(project_id), "year": year},
    )
    row = current.fetchone()
    if row:
        result_data["current_unadjusted"] = float(row.unadj)

    # 上期未审数
    prior_year = year - 1
    prior = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = '1141'
        """),
        {"pid": str(project_id), "year": prior_year},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"合同资产1141: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"

    return {"summary": summary, **result_data}


# ═══════════════════════════════════════════════════════════════════════════════
# Resolver: d6_impairment_tb — 坏账准备相关科目期初/期末未审数
# ═══════════════════════════════════════════════════════════════════════════════

# 合同资产的备抵科目（标准科目表实证，2026-08-01）：
#   * `1142 合同资产减值准备`（direction=credit）—— 准则设置的专用备抵科目
#   * `1231-05 坏账准备-合同资产`（direction=credit）—— 部分客户把合同资产减值
#     并入「坏账准备」科目族下的细分码
# 两者并列查询（客户二选一，取并集不会双算）。
#
# 🔴 原登记 `["114101", "1141.01"]` 是**把资产科目自己的子科目当备抵**（1141 是借方
#    资产科目，其子科目仍是资产明细，不是备抵）；再往前是 `["140201","1402.01"]`，
#    连科目族都错（1402 = 在途物资）。两版都取不到减值准备数据。
_IMPAIRMENT_ACCOUNT_CODES = ["1142", "1231-05"]


@auto_resolver("d6_impairment_tb")
async def _resolve_d6_impairment_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 获取合同资产减值准备相关科目的本期/上期未审数。

    查询逻辑：按 `_IMPAIRMENT_ACCOUNT_CODES`（`1142` 合同资产减值准备 /
    `1231-05` 坏账准备-合同资产）精确匹配求和。

    🔴 原 docstring 声称「第 2 步：若无结果则模糊匹配 LIKE '1141%' 且 direction='贷'」，
    但代码里**只有精确匹配、没有第 2 步**（死文档）。已按实际实现改写。

    Returns:
        {
            "summary": str,
            "prior_unadjusted": float,
            "current_unadjusted": float,
        }
    """
    result_data: dict[str, Any] = {
        "prior_unadjusted": 0.0,
        "current_unadjusted": 0.0,
    }

    # 尝试精确匹配
    codes_list = _IMPAIRMENT_ACCOUNT_CODES
    current = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = ANY(:codes)
        """),
        {"pid": str(project_id), "year": year, "codes": codes_list},
    )
    row = current.fetchone()
    if row:
        result_data["current_unadjusted"] = float(row.unadj)

    prior_year = year - 1
    prior = await db.execute(
        sa.text("""
            SELECT COALESCE(SUM(unadjusted_amount), 0) AS unadj
            FROM trial_balance
            WHERE project_id = :pid AND year = :year AND is_deleted = false
              AND standard_account_code = ANY(:codes)
        """),
        {"pid": str(project_id), "year": prior_year, "codes": codes_list},
    )
    row = prior.fetchone()
    if row:
        result_data["prior_unadjusted"] = float(row.unadj)

    cur = result_data["current_unadjusted"]
    pri = result_data["prior_unadjusted"]
    summary = f"合同资产减值准备: 期末未审={cur:,.0f}，期初未审={pri:,.0f}"

    return {"summary": summary, **result_data}
