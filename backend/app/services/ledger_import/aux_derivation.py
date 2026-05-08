"""辅助表从主表自动派生。

职责（design §6 / requirements 需求 4）：
- 余额表行含辅助维度 → 分流到 tb_balance + tb_aux_balance
- 序时账行含辅助维度 → 分流到 tb_ledger + tb_aux_ledger
- 辅助维度为空的行 → 只写主表

算法：
1. 所有行都写入主表（main_rows = 全量）
2. 对每行检查辅助维度字段（aux_dimensions_raw / aux_type / aux_code / aux_name）
3. 有非空辅助维度的行 → 解析后生成 aux_row（含 aux_type/aux_code/aux_name）
4. 一行可能有多个辅助维度（逗号分隔），每个维度生成一条 aux_row
"""

from __future__ import annotations

from typing import Any

from .aux_dimension import parse_aux_dimension

__all__ = ["derive_aux_rows"]

# Standard aux fields that indicate presence of auxiliary dimensions
_AUX_FIELDS = ("aux_type", "aux_code", "aux_name", "aux_dimensions_raw")


def derive_aux_rows(
    rows: list[dict[str, Any]],
    aux_column_indices: list[int],
    original_headers: list[str],
    table_type: str,  # "balance" or "ledger"
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into main table rows and auxiliary table rows.

    Args:
        rows: Transformed rows (standard field keys).
        aux_column_indices: Column indices identified as aux dimension columns.
        original_headers: Original headers for looking up aux column names.
        table_type: "balance" or "ledger" — determines target aux table.

    Returns:
        (main_rows, aux_rows)
        - main_rows: All rows (written to tb_balance or tb_ledger)
        - aux_rows: Rows that have non-empty aux dimensions
          (written to tb_aux_balance or tb_aux_ledger).
          Each aux_row has additional fields: aux_type, aux_code, aux_name,
          aux_dimensions_raw.
    """
    main_rows: list[dict[str, Any]] = []
    aux_rows: list[dict[str, Any]] = []

    for row in rows:
        main_rows.append(row)

        # Collect raw aux dimension text from the row
        raw_aux_text = _extract_aux_text(row, aux_column_indices, original_headers)

        if not raw_aux_text:
            continue

        # Parse aux dimensions and create aux rows
        dimensions = parse_aux_dimension(raw_aux_text)

        if not dimensions:
            continue

        for dim in dimensions:
            aux_row = dict(row)  # shallow copy
            aux_row["aux_type"] = dim.get("aux_type")
            aux_row["aux_code"] = dim.get("aux_code")
            aux_row["aux_name"] = dim.get("aux_name")
            aux_row["aux_dimensions_raw"] = raw_aux_text
            aux_rows.append(aux_row)

    return main_rows, aux_rows


def _extract_aux_text(
    row: dict[str, Any],
    aux_column_indices: list[int],
    original_headers: list[str],
) -> str:
    """Extract non-empty auxiliary dimension text from a row.

    Priority:
    1. Standard field 'aux_dimensions_raw' (if non-empty)
    2. Values from detected aux columns (by index)
    3. Other standard aux fields (aux_type, aux_code, aux_name)

    Returns combined text or empty string.
    """
    parts: list[str] = []

    # Check aux_dimensions_raw first (most common case)
    raw = row.get("aux_dimensions_raw")
    if raw and str(raw).strip():
        return str(raw).strip()

    # Check values from aux column indices
    for idx in aux_column_indices:
        if idx < len(original_headers):
            header = original_headers[idx]
            value = row.get(header)
            if value and str(value).strip():
                parts.append(str(value).strip())

    if parts:
        return "; ".join(parts)

    # Fallback: check standard aux fields for type:code name pattern
    aux_type = row.get("aux_type")
    aux_code = row.get("aux_code")
    aux_name = row.get("aux_name")

    if aux_type and str(aux_type).strip():
        # Reconstruct a parseable string
        t = str(aux_type).strip()
        c = str(aux_code).strip() if aux_code else ""
        n = str(aux_name).strip() if aux_name else ""
        if c and n:
            return f"{t}:{c} {n}"
        elif n:
            return f"{t}: {n}"
        elif c:
            return f"{t}:{c}"
        return t

    return ""
