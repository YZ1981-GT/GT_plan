"""H3 投资性房地产 Auto Data Resolvers — 从科目真源取数 / 租金收入.

科目码引用 `four_table.h3_account_scope` 的声明，不硬编码字面量。
render 走完整语义定位（按科目名逐项目），auto_resolver 用兜底码做轻量取数
（程序表步骤填充不需要精确到逐项目定位，兜底码在标准表里是正确的）。

🔴 2026-08-03 纠正：旧实现取 `1503`（可供出售金融资产）/ `1504`（债权投资），
两者都不是投资性房地产。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver
from app.services.four_table.h3_account_scope import H3_ACCOUNT_SPEC, H3_SLOT_KEY_PREFIX

logger = logging.getLogger(__name__)


def _h3_fallback_codes() -> dict[str, list[str]]:
    """从 H3_ACCOUNT_SPEC 单一真源提取兜底码。"""
    return {
        slot.key: list(slot.fallback_standard_codes)
        for slot in H3_ACCOUNT_SPEC.slots
        if slot.fallback_standard_codes
    }


@auto_resolver("h3_tb_unadjusted")
async def _resolve_h3_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 按 H3_ACCOUNT_SPEC 声明的兜底码取投资性房地产各层未审数。

    动态构造查询：从单一真源提取全部兜底码，按槽键分桶聚合。
    """
    codes_by_slot = _h3_fallback_codes()
    all_codes = [c for codes in codes_by_slot.values() for c in codes]
    if not all_codes:
        return {"summary": "⚠️ H3 无兜底科目码声明", "_error": True}

    # 按槽聚合
    slot_amounts: dict[str, dict[str, float]] = {
        slot_key: {"unadjusted": 0.0, "audited": 0.0}
        for slot_key in codes_by_slot
    }

    try:
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code = ANY(:codes)
            """),
            {"pid": str(project_id), "year": year, "codes": all_codes},
        )
        for row in result.fetchall():
            code = (row.standard_account_code or "").strip()
            # 按最长前缀匹配归槽
            for slot_key, slot_codes in codes_by_slot.items():
                if any(code == sc or code.startswith(sc + ".") or code.startswith(sc + "-") for sc in slot_codes):
                    slot_amounts[slot_key]["unadjusted"] += float(row.unadjusted_amount or 0)
                    slot_amounts[slot_key]["audited"] += float(row.audited_amount or 0)
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("h3_tb_unadjusted resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    # 组装输出（保持既有接口兼容：ip_unadjusted / dep_unadjusted / net_unadjusted）
    ip_unadjusted = slot_amounts.get("gross", {}).get("unadjusted", 0.0)
    ip_audited = slot_amounts.get("gross", {}).get("audited", 0.0)
    dep_unadjusted = (
        slot_amounts.get("accum_dep", {}).get("unadjusted", 0.0)
        + slot_amounts.get("accum_amort", {}).get("unadjusted", 0.0)
    )
    dep_audited = (
        slot_amounts.get("accum_dep", {}).get("audited", 0.0)
        + slot_amounts.get("accum_amort", {}).get("audited", 0.0)
    )
    net_unadjusted = ip_unadjusted - dep_unadjusted

    gross_codes = codes_by_slot.get("gross", [])
    summary = (
        f"H3: {'/'.join(gross_codes)}原值未审={ip_unadjusted:,.0f}，"
        f"折旧摊销未审={dep_unadjusted:,.0f}，"
        f"净值未审={net_unadjusted:,.0f}"
    )
    return {
        "summary": summary,
        "ip_unadjusted": ip_unadjusted,
        "dep_unadjusted": dep_unadjusted,
        "ip_audited": ip_audited,
        "dep_audited": dep_audited,
        "net_unadjusted": net_unadjusted,
        "account_codes": all_codes,
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
