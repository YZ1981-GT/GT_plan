"""多 sheet 合并策略 — auto / by_month / manual。

职责（见 design.md §15 / Sprint 2 Task 27-28）：

- ``auto``     : 按 (table_type, 标准化必填列签名) 聚类，同签名 sheet 合并为同一张表。
- ``by_month`` : 针对序时账，sheet 名匹配 ``^\\d{1,2}月`` 或 ``^(0[1-9]|1[0-2])``
  时按月拆分合并；非月份 sheet 走 auto 策略。
- ``manual``   : 前端勾选把几个 sheet 视为同一表，传 ``merge_groups: [[(f,s)]]``。

去重：合并后按 ``(voucher_date, voucher_no, entry_seq)`` 去重（保留首条）。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .detection_types import SheetDetection, TableType

__all__ = [
    "MergedGroup",
    "merge_sheets",
    "auto_merge",
    "by_month_merge",
    "manual_merge",
    "dedup_rows",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class MergedGroup(BaseModel):
    """A group of sheets that should be merged into one logical table."""

    table_type: TableType
    sheets: list[tuple[str, str]]  # (file_name, sheet_name) pairs
    strategy: Literal["auto", "by_month", "manual"]
    dedup_key: tuple[str, ...] = ("voucher_date", "voucher_no", "entry_seq")


# ---------------------------------------------------------------------------
# Month-pattern regex (used by by_month strategy)
# ---------------------------------------------------------------------------

_MONTH_PATTERN = re.compile(r"^\d{1,2}月|^(0[1-9]|1[0-2])\b")


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


def auto_merge(sheets: list[SheetDetection]) -> list[MergedGroup]:
    """Group sheets by (table_type, frozenset of standard_fields with confidence >= 60).

    Each group with >= 1 sheet becomes a MergedGroup with strategy="auto".
    Single-sheet groups are still returned (they represent a standalone table).

    Design ref: §15.1
    """
    groups: dict[tuple[TableType, frozenset[str]], list[tuple[str, str]]] = {}

    for s in sheets:
        required_fields = frozenset(
            m.standard_field
            for m in s.column_mappings
            if m.standard_field and m.confidence >= 60
        )
        sig = (s.table_type, required_fields)
        groups.setdefault(sig, []).append((s.file_name, s.sheet_name))

    result: list[MergedGroup] = []
    for (table_type, _fields), sheet_pairs in groups.items():
        result.append(
            MergedGroup(
                table_type=table_type,
                sheets=sheet_pairs,
                strategy="auto",
            )
        )
    return result


def by_month_merge(sheets: list[SheetDetection]) -> list[MergedGroup]:
    """Filter sheets whose sheet_name matches month patterns, group by table_type.

    Non-month sheets go through auto_merge separately.
    Return combined list.

    Design ref: §15.2
    """
    month_sheets: list[SheetDetection] = []
    non_month_sheets: list[SheetDetection] = []

    for s in sheets:
        if _MONTH_PATTERN.search(s.sheet_name):
            month_sheets.append(s)
        else:
            non_month_sheets.append(s)

    # Group month sheets by table_type
    month_groups: dict[TableType, list[tuple[str, str]]] = {}
    for s in month_sheets:
        month_groups.setdefault(s.table_type, []).append((s.file_name, s.sheet_name))

    result: list[MergedGroup] = []
    for table_type, sheet_pairs in month_groups.items():
        result.append(
            MergedGroup(
                table_type=table_type,
                sheets=sheet_pairs,
                strategy="by_month",
            )
        )

    # Non-month sheets go through auto_merge
    if non_month_sheets:
        result.extend(auto_merge(non_month_sheets))

    return result


def manual_merge(
    merge_groups: list[list[tuple[str, str]]],
    sheets: list[SheetDetection],
) -> list[MergedGroup]:
    """User-specified merge groups.

    Each inner list is a set of (file_name, sheet_name) to merge.
    Look up table_type from the first sheet in each group.
    Return MergedGroups with strategy="manual".

    Design ref: §15.3
    """
    # Build lookup: (file_name, sheet_name) -> SheetDetection
    lookup: dict[tuple[str, str], SheetDetection] = {
        (s.file_name, s.sheet_name): s for s in sheets
    }

    result: list[MergedGroup] = []
    for group in merge_groups:
        if not group:
            continue
        # Determine table_type from the first sheet in the group
        first_key = group[0]
        first_sheet = lookup.get(first_key)
        table_type: TableType = first_sheet.table_type if first_sheet else "unknown"

        result.append(
            MergedGroup(
                table_type=table_type,
                sheets=group,
                strategy="manual",
            )
        )
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def merge_sheets(
    sheets: list[SheetDetection],
    strategy: Literal["auto", "by_month", "manual"] = "auto",
    manual_groups: list[list[tuple[str, str]]] | None = None,
) -> list[MergedGroup]:
    """Dispatch to the appropriate merge function based on strategy.

    This is the main entry point for the merge module.

    Args:
        sheets: List of detected sheets to merge.
        strategy: One of "auto", "by_month", "manual".
        manual_groups: Required when strategy="manual". Each inner list is
            a set of (file_name, sheet_name) pairs to merge together.

    Returns:
        List of MergedGroup instances.
    """
    if strategy == "auto":
        return auto_merge(sheets)
    elif strategy == "by_month":
        return by_month_merge(sheets)
    elif strategy == "manual":
        return manual_merge(manual_groups or [], sheets)
    else:
        # Fallback to auto for unknown strategies
        return auto_merge(sheets)


# ---------------------------------------------------------------------------
# Deduplication (Task 28)
# ---------------------------------------------------------------------------


def dedup_rows(
    rows: list[dict],
    key_fields: tuple[str, ...] = ("voucher_date", "voucher_no", "entry_seq"),
) -> list[dict]:
    """Remove duplicate rows based on the key tuple.

    Preserves first occurrence order. Handles None values in key fields
    gracefully (treats None as a distinct value that can match other Nones).

    Args:
        rows: List of row dicts to deduplicate.
        key_fields: Tuple of field names forming the dedup key.

    Returns:
        Deduplicated list of dicts (first occurrence preserved).
    """
    seen: set[tuple] = set()
    result: list[dict] = []

    for row in rows:
        # Build key tuple; use None directly (it's hashable)
        key = tuple(row.get(f) for f in key_fields)
        if key not in seen:
            seen.add(key)
            result.append(row)

    return result
