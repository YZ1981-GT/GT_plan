"""F2 存货特殊组 — 专属渲染策略."""

from __future__ import annotations

import logging

import sqlalchemy as sa

from ._context import RenderContext, project_classification_of

logger = logging.getLogger(__name__)

CONTRACT_SHEETS = ["F2-55A", "F2-55", "F2-56", "F2-57", "F2-58"]
IPO_SHEETS = [
    "F2-61A", "F2-61", "F2-62", "F2-63", "F2-64",
    "F2-65", "F2-66", "F2-67", "F2-68", "F2-69",
    "F2-70", "F2-71", "F2-72",
]
SPECIAL_SHEETS = CONTRACT_SHEETS + IPO_SHEETS


async def render(ctx: RenderContext) -> dict | None:
    wp_id = ctx.wp_id
    db = ctx.db

    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'F2-5%' OR item_id LIKE 'F2-6%' OR item_id IN ('F2-55A', 'F2-61A')) "
                "LIMIT 1200"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("F2 special render: checklist_responses 失败: %s", e)

    # IPO 专项组可见性：项目分类 / 场景单一解释（R4）。原先按分类列精确匹配中文别名
    # {"IPO", "上市公司年审", "新三板", "重大资产重组"}，与前端 isF2IpoProject 口径一致的是资本市场类标签。
    is_ipo_project = project_classification_of(ctx).is_capital_market

    visible_sheets = list(CONTRACT_SHEETS)
    if is_ipo_project:
        visible_sheets.extend(IPO_SHEETS)

    return {
        "special_sheets": SPECIAL_SHEETS,
        "visible_sheets": visible_sheets,
        "is_ipo_project": is_ipo_project,
        "responses_snapshot": responses_snapshot,
    }
