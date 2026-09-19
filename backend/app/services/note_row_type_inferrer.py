"""附注行类型推断服务

提供 row_type 推断逻辑，可被 sidecar 生成、merge、引擎重生成等模块复用。

推断优先级：
1. 行已有 row_type → 映射为标准枚举值
2. is_total == True → total / subtotal（含"小计"则 subtotal）
3. label 为空 → blank
4. label 含"合计" → total
5. label 含"小计" → subtotal
6. label 含"提示"/"注："/"【" → note_tip
7. 否则 → data

Validates: Requirements 3.2, 3.4, 3.5
"""

from __future__ import annotations

from typing import Any


# 模板中 row_type 到标准枚举的映射
_ROW_TYPE_MAPPING: dict[str, str] = {
    "header_label": "group_header",
    "total": "total",
    "subtotal": "subtotal",
    "data": "data",
    "table_title": "table_title",
    "group_header": "group_header",
    "note_tip": "note_tip",
    "footnote": "footnote",
    "blank": "blank",
    "custom": "custom",
}

# 标准枚举合法值
VALID_ROW_TYPES: set[str] = {
    "table_title",
    "group_header",
    "data",
    "subtotal",
    "total",
    "note_tip",
    "footnote",
    "blank",
    "custom",
}


def infer_row_type(row: dict[str, Any]) -> str:
    """根据行数据推断 row_type。

    Args:
        row: 行字典，可能含 row_type / is_total / label / values 字段

    Returns:
        标准 row_type 枚举字符串
    """
    # 1. 已有 row_type：映射为标准值
    existing = row.get("row_type", "")
    if isinstance(existing, str) and existing.strip():
        mapped = _ROW_TYPE_MAPPING.get(existing.strip(), existing.strip())
        if mapped in VALID_ROW_TYPES:
            return mapped

    label = ""
    raw_label = row.get("label")
    if isinstance(raw_label, str):
        label = raw_label.strip()

    is_total = row.get("is_total", False)

    # 2. is_total 标志
    if is_total:
        if "小计" in label:
            return "subtotal"
        return "total"

    # 3. label 为空/空白 → blank
    if not label or label in (" ",):
        return "blank"

    # 4. label 含"合计" → total
    if "合计" in label:
        return "total"

    # 5. label 含"小计" → subtotal
    if "小计" in label:
        return "subtotal"

    # 6. label 含提示性关键词 → note_tip
    if "提示" in label or label.startswith("注：") or label.startswith("【"):
        return "note_tip"

    # 7. 默认 → data
    return "data"


def enrich_table_data_with_row_types(
    table_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """为 table_data 中的 _tables 行添加 row_type sidecar，不改变 values。

    规则：
    - 遍历 table_data["_tables"] 中每张表的 rows
    - 对每行调用 infer_row_type 推断
    - 已有 row_type 的行保持不变（推断结果与已有一致）
    - 不修改 values / _cell_modes / _cell_meta
    - 返回新的 table_data 副本（不修改原始入参）

    Args:
        table_data: disclosure_note.table_data 字典

    Returns:
        enriched table_data 字典（浅拷贝 + 行级 row_type 注入）
    """
    if not isinstance(table_data, dict):
        return {}

    # 浅拷贝顶层
    result = dict(table_data)

    # 处理 _tables 数组
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        enriched_tables = []
        for tbl in tables:
            if not isinstance(tbl, dict):
                enriched_tables.append(tbl)
                continue
            enriched_tbl = dict(tbl)
            rows = tbl.get("rows")
            if isinstance(rows, list):
                enriched_rows = []
                for row in rows:
                    if not isinstance(row, dict):
                        enriched_rows.append(row)
                        continue
                    enriched_row = dict(row)
                    enriched_row["row_type"] = infer_row_type(row)
                    enriched_rows.append(enriched_row)
                enriched_tbl["rows"] = enriched_rows
            enriched_tables.append(enriched_tbl)
        result["_tables"] = enriched_tables

    # 处理顶层 rows（单表兼容模式）
    top_rows = table_data.get("rows")
    if isinstance(top_rows, list) and top_rows:
        enriched_top_rows = []
        for row in top_rows:
            if not isinstance(row, dict):
                enriched_top_rows.append(row)
                continue
            enriched_row = dict(row)
            enriched_row["row_type"] = infer_row_type(row)
            enriched_top_rows.append(enriched_row)
        result["rows"] = enriched_top_rows

    return result
