"""业务视图 JSON 内存源取数器（advanced-query-linkage-closure 任务 7，design §3.2；从 ``routers/custom_query`` 原样迁入）。

- ``disclosure``：附注（单体 ``disclosure_notes`` 优先，合并 ``consol_note_data`` 兜底）；
- ``worksheet``：合并试算表 / 合并工作底稿（``consol_worksheet_data``）；
- ``workpaper_cells``：底稿单元格区域取数与 sheet 选区器预览（只读改造在任务 16）。

这些源的结果来自 JSON 列或 xlsx，只能在内存里分页：分派层（``business_fetchers``）给每行加隐藏列 ``_row_index``
（取数顺序）、行数超过 ``FETCH_HARD_CAP`` 即 400，且不支持结构化条件。
"""

from __future__ import annotations

from app.services.custom_query.pagination import FETCH_HARD_CAP


def effective_fetch_limit(limit: int | None) -> int:
    """取数器 SQL 实际使用的 LIMIT 值（原 ``routers.custom_query._effective_limit``）。

    ``limit=None`` 表示调用方不施加展示截断；SQL 仍必须有硬上限（``tb_ledger`` 百万行级，``LIMIT NULL`` 一次即打满
    内存与连接），故 None 归一为 :data:`FETCH_HARD_CAP`。触顶时分派层按 ``RESULT_TOO_LARGE`` 拒绝，不返回截断结果。
    """
    if limit is None:
        return FETCH_HARD_CAP
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return FETCH_HARD_CAP
    return max(1, min(value, FETCH_HARD_CAP))
