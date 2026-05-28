"""Sprint A.2.10 — is_empty 计算（章节空判定）.

提供两个纯函数判定附注 table 或章节是否为「空」，供 D5 auto_trim_v2 用：

- ``is_table_data_empty(table_data, *, threshold)`` — 单 table 判空
- ``is_section_empty(note, *, threshold)`` — 整章节判空（含 text_content + tables）

定义
----
**「空」语义**：所有 ``data + dynamic_data`` 行的 values 中：
  - 数值类的绝对值都 ≤ threshold（默认 0）
  - 文本类 trim 后非空 → 视为「非空」（即整张表非空）
  - 跳过的 row_type：``header_label / dynamic_anchor / dynamic_marker_end /
    total / subtotal``（这些行不参与判空）

边界
----
- ``rows`` 列表本身为空 → True
- ``table_data`` 为 None / 非 dict → True（无内容即空）
- 多表 schema（``_tables``）：只要任一张表非空 → False
- ``threshold`` 必须 ≥ 0，负数会被钳制到 0

章节判空（``is_section_empty``）
-----------------------------
- ``text_content`` trim 后非空 → False（章节有文字）
- ``table_data`` 非空 → False
- 否则 → True

入参支持 dict 和 ``DisclosureNote`` ORM 实例两种（duck-typing 取 attr / item）。

Validates: Requirements R1.5 / Sprint A.2.10 + D5 auto_trim_v2 前置
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 不参与判空的 row_type（这些行不算「数据」）
_SKIP_ROW_TYPES = frozenset(
    {
        "header_label",
        "dynamic_anchor",
        "dynamic_marker_end",
        "total",
        "subtotal",
    }
)


def _is_total_row(row: dict[str, Any]) -> bool:
    """合计行判定（与 note_total_recalc.is_total_row 同语义）."""
    if row.get("is_total") is True:
        return True
    rt = row.get("row_type")
    return isinstance(rt, str) and rt in {"subtotal", "total"}


def _to_decimal_or_text(x: Any) -> tuple[Decimal | None, str | None]:
    """尝试把 cell 值解析成数字 (Decimal) 或文本 (str)；返回 (numeric, text).

    - None / bool → (None, None)
    - Decimal / int / float → (value, None)
    - str：先尝试 Decimal；失败 → (None, trimmed_str)
    - 其他 → (None, None)
    """
    if x is None or isinstance(x, bool):
        return None, None
    if isinstance(x, Decimal):
        return x, None
    if isinstance(x, int | float):
        try:
            return Decimal(str(x)), None
        except Exception:
            return None, None
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None, None
        try:
            return Decimal(s), None
        except Exception:
            return None, s
    return None, None


def _row_is_data_row(row: dict[str, Any]) -> bool:
    """判定行是否参与 is_empty 检查."""
    if not isinstance(row, dict):
        return False
    if _is_total_row(row):
        return False
    rt = row.get("row_type")
    if isinstance(rt, str) and rt in _SKIP_ROW_TYPES:
        return False
    return True


def _rows_have_any_value(
    rows: list[Any], *, threshold: Decimal
) -> bool:
    """检查 rows 中是否存在任何「非空」cell.

    返回 True 表示至少有一格非空（→ table 整体非空）。
    """
    for r in rows:
        if not isinstance(r, dict):
            continue
        if not _row_is_data_row(r):
            continue
        vals = r.get("values")
        if not isinstance(vals, list):
            continue
        for v in vals:
            num, text = _to_decimal_or_text(v)
            if text is not None:
                # 任何非空字符串都算非空
                return True
            if num is not None and abs(num) > threshold:
                return True
    return False


def is_table_data_empty(
    table_data: dict[str, Any] | None,
    *,
    threshold: float | int = 0.0,
) -> bool:
    """判定 table_data 是否「空」.

    Args:
        table_data: dict / None
        threshold: 数值绝对值 ≤ threshold 视为空（默认 0）

    Returns:
        bool — True 表示空（所有 data 行的 values 都是 None / 0 / 空字符串）
    """
    if not isinstance(table_data, dict):
        return True

    # threshold 钳制
    try:
        thr = Decimal(str(threshold))
        if thr < 0:
            thr = Decimal("0")
    except Exception:
        thr = Decimal("0")

    # 多表分支
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        for tbl in tables:
            if not isinstance(tbl, dict):
                continue
            rows = tbl.get("rows")
            if not isinstance(rows, list) or not rows:
                continue
            if _rows_have_any_value(rows, threshold=thr):
                return False
        return True

    # 单表
    rows = table_data.get("rows")
    if not isinstance(rows, list) or not rows:
        return True
    return not _rows_have_any_value(rows, threshold=thr)


def _read_attr(obj: Any, key: str, default: Any = None) -> Any:
    """从 dict 或对象上读取 key（duck-typing）."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def is_section_empty(
    note: Any,
    *,
    threshold: float | int = 0.0,
) -> bool:
    """章节级空判定：text_content 空 + 所有 table 空 → True.

    Args:
        note: dict 或 DisclosureNote ORM 实例（含 text_content / table_data）
        threshold: 数值阈值（透传给 is_table_data_empty）

    Returns:
        bool — True 表示整章节为空（D5 auto_trim_v2 可以删除该章节）
    """
    if note is None:
        return True

    text_content = _read_attr(note, "text_content")
    if isinstance(text_content, str) and text_content.strip():
        return False

    table_data = _read_attr(note, "table_data")
    if not is_table_data_empty(table_data, threshold=threshold):
        return False

    return True


__all__ = ["is_table_data_empty", "is_section_empty"]
