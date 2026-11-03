"""核对表模板加载的统一入口（spec attachment-archive-and-a-class-evidence ADR-AE-11）。

改造前「xlsx 列映射 → 否则 docx」的分派在三个渲染入口各写一遍（checklist-table / review-checklist 渲染策略、
完成阶段 Bundle Tab 端点）。A30 底稿清单核对表要加第三种来源，再各改三处就会再次漂移 ⇒ 收口到这里。
"""

from __future__ import annotations


async def load_checklist_template(wp_code: str) -> dict:
    """底稿清单（A30）→ xlsx 列映射核对表 → docx 核对表；模板不存在抛 FileNotFoundError。"""
    from app.services.checklist_index_parser import get_index_checklist_template, is_index_checklist

    if is_index_checklist(wp_code):
        return await get_index_checklist_template(wp_code)

    from app.services.checklist_xlsx_parser import get_checklist_xlsx_template, is_xlsx_checklist

    if is_xlsx_checklist(wp_code):
        return await get_checklist_xlsx_template(wp_code)

    from app.services.checklist_docx_parser import get_checklist_template

    return await get_checklist_template(wp_code)
