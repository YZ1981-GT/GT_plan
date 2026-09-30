# -*- coding: utf-8 -*-
"""D5/D6/D7 扩容面契约 sheets[] 构建 —— 三家共用单一实现。

spec: d567-sync-coverage-via-row-table-engine

🔴 三家 provider 已被重构成 `build_orchestration(Phase5EntryConfig(...))` 配置驱动模式，
   `build_contract_payload` 仍在各 provider 里（配置的 `build_contract_payload_fn`），
   这是扩容 sheet 的正确接入点。本模块提供三家共用的构建函数，避免三份复制。

🔴 **按 sheet_key 分组**：双区两个 spec 共享同一 sheet_key（同 managed_sheet），必须归入
   **同一个** sheets[] 条目的 tables[]，否则契约解析器报「sheet_key 重复」。
"""
from __future__ import annotations

from typing import Any


def build_expansion_sheets(managed_row_table_specs: Any) -> list[dict[str, Any]]:
    """把扩容面行表 spec 列表翻成契约 sheets[] 条目（按 sheet_key 分组）。

    :param managed_row_table_specs: 各家 expansion 模块的 `managed_row_table_specs()` 返回值
    """
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    sheets: list[dict[str, Any]] = []
    by_sheet_key: dict[str, dict[str, Any]] = {}

    for spec in managed_row_table_specs:
        anchor_row = spec.header_row or spec.first_data_row - 1
        fields: list[dict[str, Any]] = []
        for column_key, column, mode, value_type, json_path, header_text, group_cell in spec.field_specs:
            field: dict[str, Any] = {
                "stable_field_key": _engine_stable_key_for(spec, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": f"源xlsx!{spec.managed_sheet}!{column}{spec.first_data_row}",
                "header_source_ref": f"源xlsx!{spec.managed_sheet}!{column}{anchor_row}",
                "store_item_id": spec.store_item_id,
                "header_text": header_text,
            }
            if group_cell:
                field["group_source_ref"] = f"源xlsx!{spec.managed_sheet}!{group_cell}"
            fields.append(field)

        table_payload = {
            "table_key": spec.table_key,
            "anchor": f"A{anchor_row}",
            "header_rows": 1,
            "row_identity": {
                "kind": "field",
                "json_pointer": f"/rows/*/{spec.row_identity_key}",
            },
            "delete_policy": "tombstone",
            "footer_anchor": {
                "marker": spec.footer_marker or "合计",
                "search_column": "A",
                "carries_total_formula": True,
            },
            "formula_mask": list(spec.formula_mask),
            "fields": fields,
        }

        entry = by_sheet_key.get(spec.sheet_key)
        if entry is None:
            entry = {
                "sheet_key": spec.sheet_key,
                "excel_name": spec.managed_sheet,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [],
            }
            by_sheet_key[spec.sheet_key] = entry
            sheets.append(entry)
        entry["tables"].append(table_payload)

    return sheets


def build_adjudication_sheet(spec: Any, *, key_prefix: str) -> list[dict[str, Any]]:
    """把一个 `AdjudicationSheetSpec` 翻成契约 sheets[] 条目（per-cell 固定行）。

    🔴 审定表无 row_identity（固定行），field 的 `cell.row_from` 用固定行号。
       契约解析器要求每个 table 至少一个 field ⇒ 给每 section 一个 item_name 锚点 field。

    :param key_prefix: stable_field_key 前缀（`d5_adj` / `d6_adj` / `d7_adj`）
    """
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    if spec is None:
        return []

    header_row = spec.header_rows[0] if spec.header_rows else spec.sections[0].title_row
    return [{
        "sheet_key": spec.sheet_key,
        "excel_name": spec.managed_sheet,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [{
            "table_key": s.table_key,
            "anchor": f"A{s.title_row}",
            "header_rows": 2,
            "first_data_row": s.first_data_row,
            "last_data_row": s.last_data_row,
            "footer_row": s.subtotal_row,
            "row_mode": spec.row_mode.value,
            "fields": [{
                "stable_field_key": f"{key_prefix}_{s.section_key}/item_name",
                "json_pointer": f"/{s.section_key}/itemName",
                "column_key": "item_name",
                "cell": {"column": "A", "row_from": s.first_data_row},
                "mode": "editable",
                "value_type": "text",
                "source_ref": f"源xlsx!{spec.managed_sheet}!A{s.first_data_row}",
                "header_source_ref": f"源xlsx!{spec.managed_sheet}!A{header_row}",
                "store_item_id": "",
                "header_text": "项目",
            }],
        } for s in spec.sections],
    }]
