"""分析性复核（analytical-review）渲染策略

当 component_type=analytical-review 时，从 trial_balance + financial_report
取数计算横向/纵向趋势 + 比率分析。

适用底稿：A1-13（母公司）、A1-14（合并）。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）"""

    from app.services.analytical_review_service import get_analytical_review_data

    db = ctx.db
    project_id = ctx.project_id
    wp_code = ctx.wp_code

    try:
        # scope: standalone for A1-13, consolidated for A1-14
        ar_scope = "consolidated" if wp_code == "A1-14" else "standalone"
        # Get year from project
        year_result = await db.execute(
            sa.text(
                "SELECT EXTRACT(YEAR FROM audit_period_end)::int "
                "FROM projects WHERE id = :pid"
            ),
            {"pid": str(project_id)},
        )
        ar_year = year_result.scalar_one_or_none() or 2025
        ar_data = await get_analytical_review_data(
            db, project_id, ar_year, wp_code, ar_scope
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("分析性复核数据获取失败 wp_code=%s: %s", wp_code, e)
        ar_data = None

    return {"analytical_review": ar_data}
