"""C-附注披露（c-note-table）渲染策略

当 component_type=c-note-table 时：
1. 若无配套 disclosure schema（sub_tables 为空）且无持久化网格 → 从模板 xlsx 提取只读网格兜底
2. 若 schema 含 fixed_cells 占位（${entity_name} 等）→ 用编制信息实际值替换

适用底稿：C 循环各附注披露底稿。
"""

from __future__ import annotations

import logging

from ._context import RenderContext

logger = logging.getLogger(__name__)


def _has_grid_cells(html_data: dict | None) -> bool:
    """判断 sheet html_data 是否已含可渲染的网格 cells。"""
    if not isinstance(html_data, dict):
        return False
    cells = html_data.get("cells")
    return isinstance(cells, dict) and len(cells) > 0


async def render(ctx: RenderContext) -> dict | None:
    """返回 sheet_html_data，None 表示不变（使用已有）。

    两段逻辑：
    ① 网格兜底：当附注披露 sheet 没有配套 render schema（无 sub_tables）且无持久化
       网格时，从模板 xlsx 提取只读网格（cells/merged_cells/样式），前端 GtWpRenderer
       用 GtGridSheet 还原模板外观（只读）。已有配套 disclosure schema 的附注走
       GtCNoteTable 结构化卡片渲染，不进此兜底。
    ② fixed_cells 占位替换：schema.fixed_cells 用 ${entity_name}/${period_end}/
       ${index_no} 等占位，GtCNoteTable 直接读 fixed_cells 渲染表头，故用编制信息
       实际值替换，避免界面显示字面量 "${entity_name}"。替换结果写回 ctx.sheet_schema。
    """
    sheet_html_data = ctx.sheet_html_data
    sheet_schema = ctx.sheet_schema

    # ─── ① 无 schema 时的只读网格兜底 ────────────────────────────────────
    if (
        not (isinstance(sheet_schema, dict) and sheet_schema.get("sub_tables"))
        and not _has_grid_cells(sheet_html_data)
    ):
        from app.services.wp_grid_extract import extract_grid

        grid: dict = {"cells": {}, "merged_cells": [], "col_widths": {}, "max_row": 0, "max_col": 0}
        if ctx.template_file_path:
            try:
                grid = extract_grid(ctx.template_file_path, ctx.classification.sheet_name)
            except Exception as e:  # noqa: BLE001 — 降级不阻塞渲染
                logger.warning(
                    "c-note 网格提取失败 %s/%s: %s",
                    ctx.template_file_path, ctx.classification.sheet_name, e,
                )

        # 合并已有持久化数据（若用户曾编辑过部分单元格）
        existing = sheet_html_data if isinstance(sheet_html_data, dict) else None
        if existing and isinstance(existing.get("cells"), dict) and existing["cells"]:
            grid = {**grid, **existing}
        sheet_html_data = grid

    # ─── ② fixed_cells 占位替换（${entity_name} 等）─────────────────────
    if (
        isinstance(sheet_schema, dict)
        and isinstance(sheet_schema.get("fixed_cells"), dict)
    ):
        from app.services.wp_preparation_info_service import build_preparation_info

        prep_info = await build_preparation_info(ctx.db, ctx.project_id, ctx.wp_id)
        subst = {
            "${entity_name}": prep_info.get("entity_name", ""),
            "${period_end}": prep_info.get("period_end", ""),
            "${index_no}": prep_info.get("index_no", "") or ctx.wp_code,
            "${page_no}": "1",
        }
        resolved_cells = {}
        for cell, val in sheet_schema["fixed_cells"].items():
            if isinstance(val, str) and val in subst:
                resolved_cells[cell] = subst[val]
            else:
                resolved_cells[cell] = val
        # 浅拷贝避免污染 schema service 缓存；写回 ctx 供主函数读取
        ctx.sheet_schema = {**sheet_schema, "fixed_cells": resolved_cells}

    return sheet_html_data
