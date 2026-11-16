"""合并附注子树重汇总的章节级来源批取。"""
from __future__ import annotations

from typing import Any

from app.services.consol_note_reaggregate_result import ACTION_PULL, _action
from app.services.consol_note_detail_source_service import load_source_tables
from app.services.consol_note_topn import section_topn_limit


async def prefetch_section_sources(run: Any, section_id: str) -> None:
    """为一次章节重汇总批取全部叶子来源，结果写入 ``run.source_tables``。

    ``run`` 是 `_Run` 编排对象；独立成伴生模块，避免主编排文件越过 800 行门，
    也让「批取一次」成为可单独静态验证的调用边界。
    """
    topn = section_topn_limit(run.template_type, section_id)
    if not topn and section_id not in run.bound_sections:
        return
    source_ids = list(dict.fromkeys(
        node.project_id
        for node in run.order
        if _action(node) == ACTION_PULL and node.project_id is not None
    ))
    if not source_ids:
        run.source_tables[section_id] = {}
        return
    run.source_tables[section_id] = await load_source_tables(
        run.db,
        source_ids,
        section_id,
        run.year,
        template_type=run.template_type,
    )
