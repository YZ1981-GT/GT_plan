"""两条账套导入链共用的用户确认列映射契约。"""
from __future__ import annotations

from typing import Any


def _mapping_dict(item: dict[str, Any]) -> dict[str, str]:
    for key in ("mappings", "column_mapping"):
        value = item.get(key)
        if isinstance(value, dict):
            return {str(header): str(field) for header, field in value.items() if field}
    entries = item.get("mapping_entries")
    if isinstance(entries, list):
        return {
            str(entry.get("original_header") or entry.get("canonical_header") or ""): str(entry.get("standard_field"))
            for entry in entries
            if isinstance(entry, dict)
            and (entry.get("original_header") or entry.get("canonical_header"))
            and entry.get("standard_field")
        }
    return {}


def normalize_custom_mapping(mapping: dict[str, Any] | None) -> dict[str, Any] | None:
    """把 v2 列表、旧「文件/工作表」字典与全局列映射统一成 canonical 形状。"""
    if not mapping:
        return None
    if isinstance(mapping.get("confirmed_mappings"), list):
        result = dict(mapping)
        result["confirmed_mappings"] = [
            {
                "file_name": str(item.get("file_name") or ""),
                "sheet_name": str(item.get("sheet_name") or ""),
                "mappings": _mapping_dict(item),
            }
            for item in mapping["confirmed_mappings"]
            if isinstance(item, dict)
        ]
        return result

    if not any(isinstance(value, dict) for value in mapping.values()):
        return {
            "confirmed_mappings": [],
            "default_mappings": dict(mapping),
        }

    confirmed: list[dict[str, Any]] = []
    for raw_key, value in mapping.items():
        if not isinstance(value, dict):
            continue
        key = str(raw_key)
        if "/" in key:
            file_name, sheet_name = key.rsplit("/", 1)
        elif "!" in key:
            file_name, sheet_name = key.rsplit("!", 1)
        else:
            file_name, sheet_name = "", key
        confirmed.append({
            "file_name": file_name,
            "sheet_name": sheet_name,
            "mappings": dict(value),
        })
    return {"confirmed_mappings": confirmed}


def resolve_sheet_mapping(
    mapping: dict[str, Any] | None,
    filename: str,
    sheet_name: str,
) -> dict[str, str] | None:
    canonical = normalize_custom_mapping(mapping)
    if not canonical:
        return None
    exact: dict[str, str] | None = None
    sheet_only: dict[str, str] | None = None
    for item in canonical.get("confirmed_mappings", []):
        item_file = str(item.get("file_name") or "")
        item_sheet = str(item.get("sheet_name") or "")
        values = dict(item.get("mappings") or {})
        if item_file == filename and item_sheet == sheet_name:
            exact = values
            break
        if not item_file and item_sheet == sheet_name:
            sheet_only = values
    selected = exact or sheet_only or canonical.get("default_mappings")
    return dict(selected) if isinstance(selected, dict) and selected else None


__all__ = ["normalize_custom_mapping", "resolve_sheet_mapping"]
