"""章节"是否含数据"判定的单一真源（纯函数）。

供 ``note_word_exporter``（Word 导出 ``_has_content``）与 ``disclosure_engine``
（``get_notes_tree`` 的 ``has_data`` 标记）复用同一口径，防止"附注树标记"与
"Word 导出结果"漂移（spec disclosure-notes-selective-generation）。

本模块只依赖入参 ``table_data`` / ``note`` 对象，无 IO、无 self 其他状态。
只被 note_word_exporter 与 disclosure_engine 引用，反向不 import 它们（无循环导入）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅类型注解，运行时不 import，避免循环导入
    from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


def effective_table_data(table_data: Any) -> Any:
    """把 ``table_data`` 投影为渲染器/判定可消费形态（纯函数版）。

    逐字节等价于 ``NoteWordExporter._effective_table_data`` 的投影逻辑：
    - ``table_data`` 不是 dict → 原样返回
    - ``project_sub_tables(table_data)`` 非空 → 返回 ``{**table_data, "_tables": projected}``
    - 投影异常 → ``logger.warning(..., exc_info=True)`` 后回退返回原 ``table_data``

    不按 ``content_type`` 分支：``_effective_table_data`` 对任意 note 都无条件调
    ``project_sub_tables``（内部按 ``_source`` 自行 no-op），是 ``table_data`` 的纯变换。
    """
    if not isinstance(table_data, dict):
        return table_data
    try:
        from app.services.note_sub_table_projector import project_sub_tables

        projected = project_sub_tables(table_data)
        if projected:
            return {**table_data, "_tables": projected}
    except Exception:  # pragma: no cover - 投影失败回退既有 _tables/rows
        logger.warning(
            "note_content_utils: sub_table projection failed, fallback to existing table_data",
            exc_info=True,
        )
    return table_data


def note_has_data(note: "DisclosureNote") -> bool:
    """判断 note 章节是否含数据（与 ``NoteWordExporter._has_content`` 同口径，单一真源）。

    - ``note.is_empty`` 为真（not_applicable）→ 短路返回 ``False``（对齐需求 Req2.4）
    - ``note.text_content`` 非空(strip 后) → ``True``
    - 否则 ``etd = effective_table_data(getattr(note,'table_data',None)) or {}``；
      ``tables = etd.get("_tables") or [etd]``；遍历每个表的 ``rows``，每行取
      ``cells = row.get("cells", row.get("values", []))``；``cell`` 是 dict →
      ``val = cell.get("value", cell.get("manual_value", 0))`` 否则 ``val = cell``；
      若 ``val and val != 0 and val != "0" and val != "-"`` → ``True``

    遍历部分用 ``try/except`` 包裹：异常 → ``logger.warning`` 后返回 ``False``
    （fail-open，供 ``get_notes_tree`` 稳定返回，不抛）。判定逻辑与 ``_has_content``
    逐字节等价，除 ``is_empty`` 短路为本函数新增前置。
    """
    if getattr(note, "is_empty", False):
        return False

    text_content = getattr(note, "text_content", None)
    if text_content and text_content.strip():
        return True

    try:
        etd = effective_table_data(getattr(note, "table_data", None)) or {}
        tables = etd.get("_tables") or [etd]
        for tbl in tables:
            if not isinstance(tbl, dict):
                continue
            rows = tbl.get("rows", [])
            for row in rows:
                values = row.get("values", [])
                cells = row.get("cells", values)
                for cell in cells:
                    if isinstance(cell, dict):
                        val = cell.get("value", cell.get("manual_value", 0))
                    else:
                        val = cell
                    if val and val != 0 and val != "0" and val != "-":
                        return True
    except Exception:  # pragma: no cover - fail-open，供 get_notes_tree 稳定返回
        logger.warning(
            "note_content_utils: note_has_data traversal failed, treat as no data",
            exc_info=True,
        )
        return False
    return False
