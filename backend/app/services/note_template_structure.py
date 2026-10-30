"""附注「🔄 恢复模板结构」取模板表结构（单体附注编辑器，Requirements 38.5 / 38.6）。

多表章节按当前表的表名找模板里的同一张表（表名比较键 ``table_key``）；只有当前表没有表名时才按序号找。
表名对不上就不返回（宁缺不错）—— 原先恒取章节第一张表：「组合计提项目：应收中央企业客户」这类后面的表点了
恢复，会被换成「按账龄披露」的行与列，2 分钟定时自动保存随即写库（2026-10-26 浏览器实测【测试】甲 五、5）。

返回表头 + 逐列定义（``columns`` / ``_column_groups``：多级表头与列身份，前端按列身份搬金额）+ 行（行名 / 行类型 /
合计标记，金额留空）；说明文字（guidance / text_after_table）不属于表结构，不返回。
"""
from __future__ import annotations

import copy
from typing import Any

from app.services.note_table_header_library import table_key

#: 模板表里随表头一起恢复的结构键
STRUCTURE_KEYS = ("columns", "_column_groups")


def pick_template_table(
    tables: Any, *, table_name: str | None = None, table_index: int | None = None,
) -> dict[str, Any] | None:
    """章节模板的表列表里取当前表对应的那张。

    给了表名：按表名比较键找，同名多张时取序号对得上的那张、否则第一张；找不到返回 None（不拿别的表顶）。
    没给表名：按序号（越界返回 None）；序号也没给（旧调用）取第一张。
    """
    items = [(i, t) for i, t in enumerate(tables if isinstance(tables, list) else []) if isinstance(t, dict)]
    if not items:
        return None
    name = str(table_name or "").strip()
    if name:
        key = table_key(name)
        hits = [(i, t) for i, t in items if table_key(t.get("name")) == key]
        if not hits:
            return None
        return next((t for i, t in hits if i == table_index), hits[0][1])
    if table_index is None:
        return items[0][1]
    return next((t for i, t in items if i == table_index), None)


def template_structure(table: dict[str, Any]) -> dict[str, Any] | None:
    """模板表 → 恢复用的结构：表头、结构键、行（金额按列宽留空）。没有表头返回 None。"""
    headers = list(table.get("headers") or [])
    if not headers:
        return None
    width = max(0, len(headers) - 1)
    rows: list[dict[str, Any]] = []
    for r in table.get("rows") or []:
        if isinstance(r, dict):
            row: dict[str, Any] = {"label": r.get("label", ""), "values": [None] * width,
                                   "is_total": bool(r.get("is_total", False))}
            if r.get("row_type"):
                row["row_type"] = r["row_type"]
        elif isinstance(r, (list, tuple)) and r:
            row = {"label": str(r[0]), "values": [None] * width, "is_total": False}
        else:
            continue
        rows.append(row)
    out: dict[str, Any] = {"name": table.get("name", ""), "headers": headers, "rows": rows}
    for key in STRUCTURE_KEYS:
        if key in table:
            out[key] = copy.deepcopy(table[key])
    return out
