"""Sprint A.2.8 — 动态行展开后的合计/小计自动重算.

设计原则
--------
- 纯函数：deepcopy 入参 → 修改副本 → 返回（不 mutate caller dict）
- 与 ``disclosure_engine._backfill_totals`` 算法等价：
    - 合计行 = ``is_total=True`` 或 ``row_type ∈ {subtotal, total}``
    - 取范围 = 上一个合计行之后到本合计行之前
    - per column：跳过 None；空列保持 None；非数字跳过
- 扩展点：``row_type`` 中的 ``dynamic_data`` / ``data`` 视为参与合计；
  ``dynamic_marker_end`` / ``header_label`` / ``dynamic_anchor`` 跳过

- 多表 schema：若 ``table_data._tables`` 是 list，则递归对每个表跑

谁负责调用？
-----------
通常在 ``dynamic_region_engine.expand_dynamic_rows`` 之后立刻跑：

    table_data = expand_dynamic_rows(table_data, ctx)
    table_data = recalc_totals_after_dynamic_expansion(table_data)

这样动态加/删的明细行被自动汇总进合计行（CI-5）。

Validates: Requirements R1.1 / Sprint A.2.8 + CI-5
"""

from __future__ import annotations

import copy
import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# 不参与合计的 row_type（与合计算法语义对齐）
_SKIP_ROW_TYPES = frozenset(
    {"header_label", "dynamic_anchor", "dynamic_marker_end"}
)
# 视为合计的 row_type（is_total 兜底）
_TOTAL_ROW_TYPES = frozenset({"subtotal", "total"})
# 视为「数据行」参与合计（除合计 + skip 之外的）
_DATA_ROW_TYPES = frozenset({"data", "dynamic_data"})


def is_total_row(row: dict[str, Any]) -> bool:
    """判定是否「合计/小计行」.

    判定优先级：
      1. ``is_total=True``                  — 旧字段（兼容）
      2. ``row_type ∈ {subtotal, total}``    — 新 D1 sidecar 字段
    """
    if not isinstance(row, dict):
        return False
    if row.get("is_total") is True:
        return True
    rt = row.get("row_type")
    return isinstance(rt, str) and rt in _TOTAL_ROW_TYPES


def is_dynamic_data_row(row: dict[str, Any]) -> bool:
    """判定是否「参与合计的数据行」.

    rules:
      - row_type ∈ {data, dynamic_data}              → True
      - row_type ∈ {header_label, dynamic_anchor,
                     dynamic_marker_end}             → False
      - row_type 缺失 + is_total 为非真 + 有 values    → True（旧数据兼容）
      - 合计行（is_total / subtotal / total）         → False
    """
    if not isinstance(row, dict):
        return False
    if is_total_row(row):
        return False

    rt = row.get("row_type")
    if isinstance(rt, str) and rt:
        if rt in _SKIP_ROW_TYPES:
            return False
        if rt in _DATA_ROW_TYPES:
            return True
        # 其他自定义 row_type → 默认参与合计（保守兼容）
        return True
    # row_type 缺失 + 非合计 → 视为数据行（兼容旧 schema）
    return True


def _to_decimal(x: Any) -> Decimal | None:
    """安全转 Decimal；非数字（含 bool / 字符串非数）→ None."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int | float):
        try:
            return Decimal(str(x))
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            return None
    return None


def _decimal_to_native(d: Decimal, sample: Any) -> Any:
    """根据原 cell 类型决定输出类型.

    - 原是 Decimal → 保留 Decimal
    - 原是 int 且 d 是整数 → int
    - 其他 → float（前端友好）
    """
    if isinstance(sample, Decimal):
        return d
    if isinstance(sample, int) and not isinstance(sample, bool):
        if d == d.to_integral_value():
            return int(d)
    try:
        return float(d)
    except Exception:
        return d


def _num_value_columns(rows: list[dict]) -> int:
    """根据 rows 中最大 values 长度推断列数."""
    n = 0
    for r in rows:
        if isinstance(r, dict):
            vals = r.get("values")
            if isinstance(vals, list):
                n = max(n, len(vals))
    return n


def _recalc_one_total_row(
    rows: list[dict],
    total_idx: int,
    num_cols: int,
) -> None:
    """重算 rows[total_idx]（合计行）的每列值.

    取范围：上一个合计行之后到 total_idx 之前的「数据行」之 sum。
    """
    # 起点：上一个合计行之后
    start = 0
    for j in range(total_idx - 1, -1, -1):
        if is_total_row(rows[j]):
            start = j + 1
            break

    cur_vals = list(rows[total_idx].get("values") or [])
    # 兜底扩展长度
    while len(cur_vals) < num_cols:
        cur_vals.append(None)

    # 找一个「样本」用于决定输出类型（取 range 中首个非 None 数值）
    sample_lookup: dict[int, Any] = {}

    for ci in range(num_cols):
        total = Decimal("0")
        has_val = False
        for r in rows[start:total_idx]:
            if not isinstance(r, dict):
                continue
            if not is_dynamic_data_row(r):
                continue
            vals = r.get("values") or []
            if ci >= len(vals):
                continue
            v = _to_decimal(vals[ci])
            if v is None:
                continue
            total += v
            has_val = True
            if ci not in sample_lookup:
                sample_lookup[ci] = vals[ci]

        if has_val:
            cur_vals[ci] = _decimal_to_native(total, sample_lookup.get(ci))
        else:
            # 整列空 → 保持 None（不强制写 0，避免「无数据 / 显式 0」歧义）
            cur_vals[ci] = None

    rows[total_idx]["values"] = cur_vals


def _recalc_rows_in_place(rows: list[dict]) -> list[dict]:
    """对 rows 列表原地重算所有合计行；返回同一 list（链式调用便利）."""
    if not isinstance(rows, list) or not rows:
        return rows
    num_cols = _num_value_columns(rows)
    if num_cols == 0:
        return rows
    for i, row in enumerate(rows):
        if isinstance(row, dict) and is_total_row(row) and i > 0:
            _recalc_one_total_row(rows, i, num_cols)
    return rows


def recalc_totals_after_dynamic_expansion(
    table_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """重算 table_data 中所有合计/小计行（含多表 _tables schema）.

    - 入参为 None / 非 dict → 返回 ``{}``
    - 单表（含 ``rows``）：直接对 rows 跑 `_recalc_rows_in_place`
    - 多表（``_tables`` 是非空 list）：每张表都跑一遍；末尾把首张表的 rows
      镜像到顶层（与 `merge_table_data_preserving_cell_modes` 行为对齐）

    返回 deepcopy 的新 dict（不 mutate 入参）。
    """
    if not isinstance(table_data, dict):
        return {}

    out = copy.deepcopy(table_data)

    tables = out.get("_tables")
    if isinstance(tables, list) and tables:
        for tbl in tables:
            if isinstance(tbl, dict):
                rows = tbl.get("rows")
                if isinstance(rows, list):
                    _recalc_rows_in_place(rows)
        # 顶层 headers/rows 镜像首张表
        first = tables[0]
        if isinstance(first, dict):
            out["rows"] = copy.deepcopy(first.get("rows", []))
            if "headers" in first:
                out["headers"] = copy.deepcopy(first.get("headers", []))
        return out

    # 单表
    rows = out.get("rows")
    if isinstance(rows, list):
        _recalc_rows_in_place(rows)

    return out


__all__ = [
    "recalc_totals_after_dynamic_expansion",
    "is_total_row",
    "is_dynamic_data_row",
]
