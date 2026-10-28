# -*- coding: utf-8 -*-
"""行表引擎的值换算（store ↔ 投影）与行内数组缺省形态。

spec: oo-writeback-template-parity-closure R3 批 B2（由 `phase5_row_table_sheet` 拆出，引擎文件逼近 800 行）。

三件事，两个方向成对：
  - percent_points：store 存百分数（3.5 = 3.5%），Excel 存小数（0.035）⇒ 投影 ÷100、回写 ×100（FC-10，原样搬来）；
  - 勾选列（`RowTableSheetSpec.boolean_unchecked_as_blank`）：未勾在 Excel 里留空、不写 FALSE（与 D4 IPO
    核查表同口径）⇒ 投影 False → None、回写 None → False；只影响该 spec 的 boolean 字段；
  - 行内数组（`RowTableSheetSpec.row_array_defaults`）：回写写 `checkItems/N` 这类数组元素前，行里没有该数组就
    先按声明建好（OO 侧新增的行、旧数据缺键）；已有数组不改长度（越界照旧 fail closed，见 `json_path`）。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.workpaper_sync.contracts import ValueType


def _is(vtype: Any, target: ValueType) -> bool:
    return vtype is not None and str(getattr(vtype, "value", vtype)) == target.value


def to_projection_value(spec: Any, value_type: Any, raw_value: Any) -> Any:
    """store 值 → 投影值（HTML → OO）。"""
    if raw_value is not None and _is(value_type, ValueType.percent_points):
        try:
            return Decimal(str(raw_value)) / Decimal("100")
        except Exception:  # noqa: BLE001 — 非数值保持原值，normalize_value 会拒绝
            return raw_value
    if raw_value is False and _is(value_type, ValueType.boolean) and getattr(spec, "boolean_unchecked_as_blank", False):
        return None
    return raw_value


def to_store_value(spec: Any, value_type: Any, new_val: Any) -> Any:
    """投影值 → store 值（OO → HTML），与 `to_projection_value` 对称。"""
    if new_val is not None and _is(value_type, ValueType.percent_points):
        try:
            return float(Decimal(str(new_val)) * Decimal("100"))
        except Exception:  # noqa: BLE001
            return new_val
    if new_val is None and _is(value_type, ValueType.boolean) and getattr(spec, "boolean_unchecked_as_blank", False):
        return False
    return new_val


def ensure_row_arrays(spec: Any, target: dict, json_path: str) -> None:
    """`json_path` 落在声明了缺省形态的数组里、而行里还没有这个数组 ⇒ 按声明建好。"""
    head = json_path.split("/", 1)[0]
    for key, length, fill in getattr(spec, "row_array_defaults", ()) or ():
        if key == head and not isinstance(target.get(key), list):
            target[key] = [fill] * int(length)
