"""H2 在建工程 Auto Data Resolvers — 科目1604 / 转固合计."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_data_resolvers import auto_resolver

logger = logging.getLogger(__name__)


@auto_resolver("h2_tb_unadjusted")
async def _resolve_h2_tb_unadjusted(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从 trial_balance 取科目1604在建工程的未审数.

    1604: 资产类/借方 — unadjusted_amount 为正数（期末余额）
    """
    cip_unadjusted = 0.0
    cip_audited = 0.0

    try:
        result = await db.execute(
            sa.text("""
                SELECT standard_account_code, unadjusted_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                  AND standard_account_code LIKE '1604%'
            """),
            {"pid": str(project_id), "year": year},
        )
        for row in result.fetchall():
            cip_unadjusted += float(row.unadjusted_amount or 0)
            cip_audited += float(row.audited_amount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("h2_tb_unadjusted resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    summary = f"H2: 1604在建工程未审={cip_unadjusted:,.0f}，审定={cip_audited:,.0f}"
    return {
        "summary": summary,
        "cip_unadjusted": cip_unadjusted,
        "cip_audited": cip_audited,
        "account_codes": ["1604"],
    }


@auto_resolver("h2_transfer_summary")
async def _resolve_h2_transfer_summary(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """从H2-5转固时点检查表取数转固合计.

    读取 checklist_responses 中 item_id='H2-5-rows' 的 conclusion JSON，
    汇总各工程的转固金额。
    """
    transfer_total = 0.0
    transfer_count = 0
    items: list[dict[str, Any]] = []

    try:
        # 查找H2相关底稿
        result = await db.execute(
            sa.text("""
                SELECT cr.conclusion
                FROM checklist_responses cr
                JOIN working_paper wp ON cr.wp_id = wp.id
                WHERE wp.project_id = :pid AND wp.is_deleted = false
                  AND cr.item_id = 'H2-5-rows'
                LIMIT 1
            """),
            {"pid": str(project_id)},
        )
        row = result.fetchone()
        if row and row.conclusion:
            try:
                rows_data = json.loads(row.conclusion)
                if isinstance(rows_data, list):
                    for item in rows_data:
                        amount = float(item.get("transferAmount", 0) or 0)
                        if amount > 0:
                            transfer_total += amount
                            transfer_count += 1
                            items.append({
                                "name": item.get("projectName", ""),
                                "amount": amount,
                            })
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as e:  # noqa: BLE001
        logger.warning("h2_transfer_summary resolver failed: %s", e)
        return {"summary": "⚠️ 数据获取失败", "_error": True}

    summary = f"H2转固: {transfer_count}项合计={transfer_total:,.0f}"
    return {
        "summary": summary,
        "transfer_total": transfer_total,
        "transfer_count": transfer_count,
        "items": items,
    }
