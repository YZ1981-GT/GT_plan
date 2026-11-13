"""附注表格稳定列身份与显示度量目录的运行时读取层。

目录由 ``scripts/gen/gen_note_table_measure_catalog.py --check`` 守护；请求期只读静态 JSON，
不按标题或数值猜 kind。匹配失败保留原值并返回 ``measure_status=unmatched|invalid``。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.contracts.display_measure import DisplayMeasureContractError, build_measure_spec

_PATH = Path(__file__).resolve().parents[2] / "data" / "note_table_measure_catalog.json"


@lru_cache(maxsize=4)
def _load(mtime_ns: int) -> tuple[dict[str, Any], ...]:
    del mtime_ns
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise ValueError("附注度量目录缺 entries")
    return tuple(row for row in entries if isinstance(row, dict))


def catalog_entries() -> tuple[dict[str, Any], ...]:
    return _load(_PATH.stat().st_mtime_ns)


def _variant(value: Any, *, consolidated: bool = False) -> str:
    raw = str(getattr(value, "value", value) or "soe").lower()
    base = "listed" if "listed" in raw else "soe"
    return f"consol_{base}" if consolidated else base


def _empty_metadata(table: dict[str, Any], status: str) -> None:
    width = len(table.get("headers") or [])
    table["measure_status"] = status
    table["column_ids"] = [None] * width
    table["column_kinds"] = [None] * width
    table["column_ratio_scales"] = [None] * width


def apply_measure_metadata(
    table: dict[str, Any], *, variant: str, section_id: str, table_index: int | None = None,
) -> str:
    """给一张响应表附上等长元数据，返回 matched/unmatched/invalid。"""
    table_id = str(table.get("table_id") or "")
    candidates = [
        row for row in catalog_entries()
        if row.get("variant") == variant and row.get("section_id") == section_id
    ]
    entry = next((row for row in candidates if table_id and row.get("table_id") == table_id), None)
    if entry is None and table_index is not None:
        entry = next((row for row in candidates if row.get("table_index") == table_index), None)
    if entry is None:
        _empty_metadata(table, "unmatched")
        return "unmatched"

    table["table_id"] = entry.get("table_id")
    columns = entry.get("columns")
    headers = table.get("headers") or []
    if not isinstance(columns, list) or len(columns) != len(headers):
        _empty_metadata(table, "invalid")
        return "invalid"
    try:
        for index, column in enumerate(columns):
            if not isinstance(column, dict) or column.get("index") != index:
                raise DisplayMeasureContractError("column index 不连续")
            build_measure_spec(column.get("kind"), column.get("ratio_scale"), locator=f"{variant}:{section_id}:{index}")
            if not column.get("column_id"):
                raise DisplayMeasureContractError("column_id 为空")
    except (DisplayMeasureContractError, TypeError, ValueError):
        _empty_metadata(table, "invalid")
        return "invalid"

    table["measure_status"] = "matched"
    table["column_ids"] = [column["column_id"] for column in columns]
    table["column_kinds"] = [column["kind"] for column in columns]
    table["column_ratio_scales"] = [column.get("ratio_scale") for column in columns]
    return "matched"


def attach_standalone_measure_metadata(
    table_data: dict[str, Any] | None, source_template: Any, section_number: str | None,
) -> None:
    if not isinstance(table_data, dict) or not section_number:
        return
    variant = _variant(source_template)
    # `source_template` 记项目模板，可能和章节实际变体不同。不要用 guidance 是否存在判断：无 guidance
    # 的表也需要稳定列 ID。目录里该章节只落在另一变体时才保守纠正；两个都有则保持声明值。
    known_variants = {
        str(row.get("variant")) for row in catalog_entries()
        if row.get("section_id") == str(section_number) and not str(row.get("variant", "")).startswith("consol_")
    }
    if variant not in known_variants and len(known_variants) == 1:
        variant = known_variants.pop()
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        for index, table in enumerate(tables):
            if isinstance(table, dict):
                apply_measure_metadata(table, variant=variant, section_id=str(section_number), table_index=index)
        return
    if isinstance(table_data.get("headers"), list):
        apply_measure_metadata(table_data, variant=variant, section_id=str(section_number), table_index=0)


def attach_consolidated_measure_metadata(section: dict[str, Any], standard: Any) -> str:
    if "table_id" not in section and section.get("id"):
        section["table_id"] = str(section["id"])
    return apply_measure_metadata(
        section,
        variant=_variant(standard, consolidated=True),
        section_id=str(section.get("section_id") or ""),
        table_index=None,
    )
