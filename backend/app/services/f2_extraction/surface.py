"""F2 公式管理面板 surfacing（供 GET /formulas 的 surfaced 字段）."""
from __future__ import annotations

import logging
from typing import Any

from app.services.f2_extraction.presets import (
    SOURCE_DISABLED,
    f2_tier_a_semantic,
    load_f2_presets,
    resolve_effective,
)

logger = logging.getLogger(__name__)


async def build_f2_surfaced_formulas(db, wp) -> list[dict]:
    """为 F2 底稿产出公式管理面板的 surfaced 条目.

    每条 = 一个有效 Tier A 取数公式绑定（预设 ∪ 用户覆盖），
    字段对齐 wp_formula.py GET /formulas 的 surfaced 条目结构：
    {id, sheet_name, target_cell, expression, formula_type, category,
     description, editable, readonly, source, semantic, sheet_codes, value}

    灰度关时不被调用（wp_surfaced_f.py 外层门控）。
    """
    wp_id = getattr(wp, "id", None) or getattr(wp, "wp_id", None)
    project_id = getattr(wp, "project_id", None)
    if not wp_id or not project_id:
        return []

    try:
        effective = await resolve_effective(db, wp_id, project_id)
    except Exception as e:
        logger.warning("build_f2_surfaced_formulas: resolve_effective 失败: %s", e)
        effective = load_f2_presets()

    items: list[dict] = []
    for i, binding in enumerate(effective):
        anchor = binding.get("anchor", "")
        source = binding.get("source", "preset")
        expression = binding.get("expression", "")

        # disabled 绑定仍展示（标记不可编辑+disabled 分类）
        is_disabled = source == SOURCE_DISABLED

        items.append({
            "id": f"F2-surfaced-{anchor}" if anchor else f"F2-surfaced-{i}",
            "sheet_name": binding.get("sheet_name", "F2-1"),
            "target_cell": anchor,
            "expression": expression,
            "formula_type": binding.get("formula_type", "auto_calc"),
            "category": "取数" if not is_disabled else "disabled",
            "description": binding.get("description", ""),
            "editable": True,
            "readonly": is_disabled,
            "source": source,
            "semantic": f2_tier_a_semantic(expression),
            "sheet_codes": ["F2-1"],
            "value": None,  # GET 面板不逐条重求值（值由 render tb_values 提供）
        })

    return items
