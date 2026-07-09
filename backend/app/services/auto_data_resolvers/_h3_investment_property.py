"""H3 投资性房地产 Auto Data Resolvers — 科目1503+1504 / 租金收入."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)

_H3_ACCOUNT_PREFIXES = ("1503", "1504")


@auto_resolver("h3_tb_unadjusted")
async def _resolve_h3_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 取科目1503投资性房地产+1504累计折旧(成本模式)的未审数.

    1503: 资产类/借方 — unadjusted_amount 为正数（期末余额）
    1504: 备抵类/贷方 — unadjusted_amount 为正数（期末余额，贷方方向）
         公允价值模式下1504无余额，但仍查询
    """
    ip_unadjusted = 0.0
    dep_unadjusted = 0.0
    ip_audited = 0.0
    dep_audited = 0.0

    try:
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND (standard_account_code LIKE '1503%' OR standard_account_code LIKE '1504%')
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            if code.startswith("1503"):
                ip_unadjusted += float(row.unadjusted_amount or 0)
                ip_audited += float(row.audited_amount or 0)
            elif code.startswith("1504"):
                dep_unadjusted += float(row.unadjusted_amount or 0)
                dep_audited += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("h3_tb_unadjusted resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    net_unadjusted = ip_unadjusted - dep_unadjusted
    summary = (
        f"H3: 1503原值未审={ip_unadjusted:,.0f}，"
        f"1504折旧未审={dep_unadjusted:,.0f}，"
        f"净值未审={net_unadjusted:,.0f}"
    )
    return {
        "summary": summary,
        "ip_unadjusted": ip_unadjusted,
        "dep_unadjusted": dep_unadjusted,
        "ip_audited": ip_audited,
        "dep_audited": dep_audited,
        "net_unadjusted": net_unadjusted,
        "account_codes": list(_H3_ACCOUNT_PREFIXES),
    }


@auto_resolver("h3_rental_income")
async def _resolve_h3_rental_income(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 H3-14 租金收入测算表取租金收入合计.

    查找关联的 H3 底稿 → 读取 H3-14-rows 数据 → 汇总 annualRent/actualIncome。
    """
    total_annual_rent = 0.0
    total_actual_income = 0.0
    asset_count = 0

    try:
        # 查找项目下 H3 底稿的 wp_id
        result = await db.execute(
            sa.text("""
                SELECT cr.conclusion
                FROM checklist_responses cr
                JOIN working_paper wp ON cr.wp_id = wp.id
                WHERE wp.project_id = :pid AND wp.is_deleted = false
                  AND cr.item_id = 'H3-14-rows'
                LIMIT 1
            """),
            {"pid": str(project_id)},
        )
        row = result.fetchone()
        if row and row.conclusion:
            try:
                rows = json.loads(row.conclusion)
                if isinstance(rows, list):
                    for item in rows:
                        asset_count += 1
                        total_annual_rent += float(item.get("annualRent", 0) or 0)
                        total_actual_income += float(item.get("actualIncome", 0) or 0)
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as e:  # noqa: BLE001
        logger.warning("h3_rental_income resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    summary = (
        f"H3-14: 租赁资产{asset_count}项，"
        f"年租金合计={total_annual_rent:,.0f}，"
        f"实际收入合计={total_actual_income:,.0f}"
    )
    return {
        "summary": summary,
        "total_annual_rent": total_annual_rent,
        "total_actual_income": total_actual_income,
        "asset_count": asset_count,
    }
