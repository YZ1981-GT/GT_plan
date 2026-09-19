"""Univer 网格（univer）渲染策略

当 component_type=univer 时，从模板 xlsx 提取只读网格数据。

混合底稿（含 HTML sheet + univer sheet）整本走 GtWpRenderer 时，
univer sheet（审定表/明细表/测算表）之前只显示死占位「数据尚未导入」，
模板网格结构完全不体现。此处补 cells/merged_cells 让模板内容可见（只读），
TB 取数后续再填。

适用底稿：所有 componentType=univer 的 sheet（默认/兜底类型）。
"""

from __future__ import annotations

import logging

from ._context import RenderContext
from ._utils import _has_grid_cells

logger = logging.getLogger(__name__)


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）"""

    sheet_html_data = ctx.sheet_html_data

    # 已有可渲染网格 → 无需重新提取
    if _has_grid_cells(sheet_html_data):
        return None

    from app.services.wp_grid_extract import extract_grid

    grid: dict = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}
    if ctx.template_file_path:
        try:
            grid = extract_grid(ctx.template_file_path, ctx.classification.sheet_name)
        except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
            logger.warning(
                "univer 网格提取失败 %s/%s: %s",
                ctx.template_file_path, ctx.classification.sheet_name, e,
            )

    # 合并已有持久化数据（若用户曾编辑过部分单元格）
    existing = sheet_html_data if isinstance(sheet_html_data, dict) else None
    if existing and isinstance(existing.get("cells"), dict) and existing["cells"]:
        grid = {**grid, **existing}

    return grid
