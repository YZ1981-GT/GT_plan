"""Sprint A.2 批 2 — wp_data 提数核心.

三种提取模式：
1. extract_wp_cell(parsed_data, sheet, cell_ref) -> value
2. extract_wp_table(parsed_data, sheet, row_filter, label_col, value_cols) -> list[{label, values}]
3. extract_wp_column_sum(parsed_data, sheet, col_letter, row_range) -> Decimal | None

输入：底稿的 ``parsed_data`` dict（已 load）
输出：值（Decimal / list / None — 缺数据不抛异常）

设计原则：
- **纯函数 / 无 DB / 无副作用** — 调用方负责加载 WorkingPaper.parsed_data
- 永不抛异常：缺数据返 None / []
- 兼容两种 cells 形态（与 wp_version_search_service / prefill_engine 对齐）：
  形态 1: ``{"Sheet1!A1": value_or_dict}``  扁平
  形态 2: ``{"Sheet1": {"A1": value_or_dict}}``  嵌套（Univer snapshot）
- value 可能是标量、``{"v": ..., "f": ...}``、``{"value": ..., "formula": ...}``

详见 design.md §一 D3 / D4 + Sprint A.2.4 任务卡。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _split_cell_ref(cell_ref: str) -> tuple[str, int] | None:
    """``"F5"`` → ``("F", 5)``；非法返 None."""
    if not isinstance(cell_ref, str):
        return None
    m = _CELL_REF_RE.match(cell_ref.strip().upper())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def _col_letter_to_index(letter: str) -> int | None:
    """``"A"`` → 1，``"AA"`` → 27；非法返 None."""
    if not isinstance(letter, str):
        return None
    s = letter.strip().upper()
    if not s or not s.isalpha():
        return None
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _extract_cell_value(raw: Any) -> Any:
    """从单元格数据提取实际值（兼容标量 / dict {value, formula} / dict {v, f}）.

    与 wp_version_search_service._extract_cell_value 对齐，且额外支持 ``value`` 键。
    """
    if isinstance(raw, dict):
        for key in ("v", "value", "val"):
            if key in raw:
                return raw[key]
        return None
    return raw


def _to_decimal(x: Any) -> Decimal | None:
    """安全转 Decimal（支持 Decimal / int / float / 数值字符串 / None）."""
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int | float):
        try:
            return Decimal(str(x))
        except (InvalidOperation, ValueError):
            return None
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None
    return None


def _get_cell_raw(parsed_data: dict, sheet: str, cell_ref: str) -> Any:
    """取 cell 原始 raw（兼容扁平 / 嵌套 两种 cells 形态）.

    缺失返 None。
    """
    if not isinstance(parsed_data, dict):
        return None
    cells = parsed_data.get("cells")
    if not isinstance(cells, dict):
        return None

    # 形态 1：扁平 "Sheet!CellRef"
    flat_key = f"{sheet}!{cell_ref}"
    if flat_key in cells:
        return cells[flat_key]

    # 形态 2：嵌套 cells[sheet][cell_ref]
    sheet_block = cells.get(sheet)
    if isinstance(sheet_block, dict) and cell_ref in sheet_block:
        return sheet_block[cell_ref]

    return None


def _iter_sheet_rows(parsed_data: dict, sheet: str) -> set[int]:
    """收集 sheet 中所有出现过的行号（1-based）.

    从扁平 ``"Sheet!A1"`` 和嵌套 ``cells[Sheet]["A1"]`` 两种形态扫描。
    """
    rows: set[int] = set()
    if not isinstance(parsed_data, dict):
        return rows
    cells = parsed_data.get("cells")
    if not isinstance(cells, dict):
        return rows

    prefix = f"{sheet}!"
    for key in cells:
        if not isinstance(key, str):
            continue
        if key.startswith(prefix):
            tail = key[len(prefix):]
            parsed = _split_cell_ref(tail)
            if parsed:
                rows.add(parsed[1])

    sheet_block = cells.get(sheet)
    if isinstance(sheet_block, dict):
        for inner in sheet_block:
            parsed = _split_cell_ref(str(inner))
            if parsed:
                rows.add(parsed[1])

    return rows


# ---------------------------------------------------------------------------
# Public API 1: extract_wp_cell
# ---------------------------------------------------------------------------


def extract_wp_cell(
    parsed_data: dict,
    sheet: str,
    cell_ref: str,
) -> Decimal | str | None:
    """从底稿单元格取值.

    cells key 格式: ``"{sheet}!{cell_ref}"``，value 可能是 number / string /
    dict ``{value, formula}`` 或 ``{v, f}``。

    返回：
    - Decimal（数值能转）
    - str（文本字段，例如审定结论）
    - None（缺失 / 空白 / 非法 ref）
    """
    if not isinstance(sheet, str) or not sheet:
        return None
    parsed = _split_cell_ref(cell_ref) if isinstance(cell_ref, str) else None
    if parsed is None:
        return None

    raw = _get_cell_raw(parsed_data, sheet, cell_ref.strip().upper())
    if raw is None:
        return None

    value = _extract_cell_value(raw)
    if value is None:
        return None

    # 数值优先（含字符串数字）
    dec = _to_decimal(value)
    if dec is not None:
        return dec

    # 文本兜底
    if isinstance(value, str):
        s = value.strip()
        return s if s else None

    return None


# ---------------------------------------------------------------------------
# Public API 2: extract_wp_table
# ---------------------------------------------------------------------------


_DEFAULT_EXCLUDE_PATTERN = "合计|小计|总计"


def _should_skip_row(
    label: str | None,
    is_total_row: bool,
    row_filter: dict | None,
) -> bool:
    """根据 row_filter 判定是否跳过此行."""
    if not isinstance(row_filter, dict):
        return False

    # is_total: 若过滤器要求 is_total=False（即排除合计），命中合计行就跳过
    is_total_flag = row_filter.get("is_total")
    if is_total_flag is False and is_total_row:
        return True
    if is_total_flag is True and not is_total_row:
        return True

    pattern = row_filter.get("exclude_label_pattern")
    if isinstance(pattern, str) and pattern and isinstance(label, str):
        try:
            if re.search(pattern, label):
                return True
        except re.error:
            logger.warning("extract_wp_table: invalid regex %r — skipping pattern", pattern)

    return False


def _looks_like_total(label: str | None) -> bool:
    """判定 label 是否为合计/小计/总计 行（不依赖 row_filter）."""
    if not isinstance(label, str):
        return False
    return bool(re.search(_DEFAULT_EXCLUDE_PATTERN, label))


def extract_wp_table(
    parsed_data: dict,
    sheet: str,
    row_filter: dict | None = None,
    label_col: str = "A",
    value_cols: dict[str, str] | None = None,
) -> list[dict]:
    """从底稿 sheet 提取多行表格数据.

    扫描 sheet 中所有有数据的行，按 ``label_col`` 取标签、按 ``value_cols``
    取每列值，跳过 ``row_filter`` 命中的行（如合计、空白）。

    Args:
        parsed_data: 底稿 ``parsed_data`` dict。
        sheet:       sheet 名（如 ``"分类构成"``）。
        row_filter:  ``{"is_total": bool, "exclude_label_pattern": regex}``；
                     None = 不过滤但仍跳过空 label 行。
        label_col:   标签列字母，如 ``"A"``。
        value_cols:  ``{col_id: col_letter}``，如 ``{"col_amount_end": "F"}``。

    Returns:
        ``[{"label": str, "values": {col_id: Decimal | None}}, ...]``；空表返 ``[]``。
    """
    if not isinstance(sheet, str) or not sheet:
        return []
    if not isinstance(label_col, str) or _col_letter_to_index(label_col) is None:
        return []

    rows = sorted(_iter_sheet_rows(parsed_data, sheet))
    if not rows:
        return []

    cols_map = value_cols if isinstance(value_cols, dict) else {}
    label_col_upper = label_col.strip().upper()

    output: list[dict] = []
    for row_num in rows:
        label_raw = _get_cell_raw(parsed_data, sheet, f"{label_col_upper}{row_num}")
        label_val = _extract_cell_value(label_raw)
        if isinstance(label_val, str):
            label = label_val.strip()
        elif label_val is None:
            label = ""
        else:
            label = str(label_val).strip()

        # 完全空行跳过（无 label 且无 values 数据）
        if not label and not cols_map:
            continue

        is_total_row = _looks_like_total(label)
        if _should_skip_row(label, is_total_row, row_filter):
            continue

        # 即便没指定 value_cols，也保留 label 行（caller 可能只需 label 列表）
        values: dict[str, Decimal | None] = {}
        all_values_empty = True
        for col_id, col_letter in cols_map.items():
            if not isinstance(col_id, str) or not isinstance(col_letter, str):
                values[str(col_id)] = None
                continue
            ref = f"{col_letter.strip().upper()}{row_num}"
            cell_raw = _get_cell_raw(parsed_data, sheet, ref)
            v = _extract_cell_value(cell_raw)
            dec = _to_decimal(v)
            values[col_id] = dec
            if dec is not None or (isinstance(v, str) and v.strip()):
                all_values_empty = False

        # 无 label + values 全空 → 跳过空白行
        if not label and all_values_empty:
            continue

        output.append({"label": label, "values": values})

    return output


# ---------------------------------------------------------------------------
# Public API 3: extract_wp_column_sum
# ---------------------------------------------------------------------------


def extract_wp_column_sum(
    parsed_data: dict,
    sheet: str,
    col_letter: str,
    row_range: tuple[int, int] | None = None,
) -> Decimal | None:
    """对 sheet 某列求和.

    Args:
        parsed_data: 底稿 ``parsed_data``。
        sheet:       sheet 名。
        col_letter:  列字母（如 ``"F"``）。
        row_range:   ``(start, end)`` 1-based 闭区间；None = 全列。

    Returns:
        Decimal 总和；列空 / 无数值 → None；非法参数 → None。
    """
    if not isinstance(sheet, str) or not sheet:
        return None
    if _col_letter_to_index(col_letter) is None:
        return None

    if row_range is not None:
        if (
            not isinstance(row_range, tuple | list)
            or len(row_range) != 2
            or not all(isinstance(x, int) for x in row_range)
        ):
            return None
        start, end = int(row_range[0]), int(row_range[1])
        if start <= 0 or end < start:
            return None
        rows_iter: list[int] = list(range(start, end + 1))
    else:
        rows_iter = sorted(_iter_sheet_rows(parsed_data, sheet))

    if not rows_iter:
        return None

    col_upper = col_letter.strip().upper()
    total = Decimal("0")
    has_value = False
    for row_num in rows_iter:
        raw = _get_cell_raw(parsed_data, sheet, f"{col_upper}{row_num}")
        v = _extract_cell_value(raw)
        dec = _to_decimal(v)
        if dec is None:
            continue
        total += dec
        has_value = True

    return total if has_value else None


__all__ = [
    "extract_wp_cell",
    "extract_wp_column_sum",
    "extract_wp_table",
]
