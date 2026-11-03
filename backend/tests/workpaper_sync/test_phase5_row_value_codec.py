# -*- coding: utf-8 -*-
"""行表引擎值换算与行内数组（spec oo-writeback-template-parity-closure R3 批 B2a，`phase5_row_value_codec`）。

🔴 一律用**真** `FieldValue`（`value_type` 是 `ValueType` 枚举）走 `merge_projection_into_store_rows`：原实现写
`str(vtype) == "percent_points"`，枚举的 str() 是「ValueType.percent_points」恒不等 ⇒ OO → HTML 的 ×100 从未
生效（F3-4 票面利率、F2-47 销售费用率 / 税率回写成 0.035 而前端按 3.5 读）。旧测试若用字符串当 value_type
就看不出来 —— 本文件的替身投影只替 `stable_keys()` / `get()`，值对象是生产类。
"""
from __future__ import annotations

import dataclasses
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.adapters.base import FieldValue  # noqa: E402
from app.services.workpaper_sync.contracts import FieldMode, ValueType  # noqa: E402
from app.services.workpaper_sync.json_path import JsonPathTypeMismatchError  # noqa: E402
from app.services.workpaper_sync.phase5_d3_07_voucher_check import SPEC_D307_CURRENT  # noqa: E402
from app.services.workpaper_sync.phase5_d7_07_inspection import SPEC_D707_POST  # noqa: E402
from app.services.workpaper_sync.phase5_f3_04_interest import SPEC_F304  # noqa: E402
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    managed_field_specs,
    merge_projection_into_store_rows,
)
from app.services.workpaper_sync.phase5_row_value_codec import (  # noqa: E402
    ensure_row_arrays,
    to_projection_value,
    to_store_value,
)


class _Proj:
    """只替身投影的取键方式；值对象是生产 `FieldValue`。"""

    def __init__(self, values: dict[str, FieldValue]) -> None:
        self._v = values

    def stable_keys(self):
        return list(self._v)

    def get(self, key):
        return self._v.get(key)


def _fv(spec, column: str, row_key: str, value, mode=FieldMode.editable) -> tuple[str, FieldValue]:
    f = next(x for x in managed_field_specs(spec) if x[1] == column)
    key = f"{spec.table_key}/{row_key}/{f[0]}"
    return key, FieldValue(stable_key=key, value=value, value_type=ValueType(f[3]), mode=mode, row_key=row_key)


def _merge(spec, base_rows, *pairs):
    rows, applied, _visited, touched = merge_projection_into_store_rows(
        spec, projection=_Proj(dict(pairs)), base_rows=base_rows
    )
    return {r[spec.row_identity_key]: r for r in rows}, applied, touched


# ═══ percent_points：两个方向 ═══


def test_percent_points_merge_scales_back_with_real_enum_value_type() -> None:
    """F3-4 G 票面利率：OO 侧 0.035 ⇒ store 3.5（原实现恒存 0.035）。"""
    rows, applied, touched = _merge(SPEC_F304, [{SPEC_F304.row_identity_key: "r1", "interestRate": 3.0}],
                                    _fv(SPEC_F304, "G", "r1", 0.035))
    assert rows["r1"]["interestRate"] == pytest.approx(3.5)
    assert applied == 1 and touched == {"r1"}


@pytest.mark.parametrize("vtype", [ValueType.percent_points, "percent_points"])
def test_percent_points_codec_accepts_enum_and_plain_string(vtype) -> None:
    assert to_projection_value(SPEC_F304, vtype, 3.5) == Decimal("0.035")
    assert to_store_value(SPEC_F304, vtype, Decimal("0.035")) == pytest.approx(3.5)
    assert to_store_value(SPEC_F304, vtype, None) is None
    assert to_store_value(SPEC_F304, vtype, "abc") == "abc"  # 非数值原样交给 normalize_value 拒收


# ═══ 勾选列：未勾留空 ═══


def test_unchecked_boolean_is_blank_only_when_spec_opts_in() -> None:
    assert SPEC_D707_POST.boolean_unchecked_as_blank
    assert to_projection_value(SPEC_D707_POST, ValueType.boolean, False) is None
    assert to_projection_value(SPEC_D707_POST, ValueType.boolean, True) is True
    assert to_store_value(SPEC_D707_POST, ValueType.boolean, None) is False
    off = dataclasses.replace(SPEC_D707_POST, boolean_unchecked_as_blank=False)
    assert to_projection_value(off, ValueType.boolean, False) is False
    assert to_store_value(off, ValueType.boolean, None) is None
    # 非 boolean 字段不受影响
    assert to_projection_value(SPEC_D707_POST, ValueType.amount, False) is False
    assert to_store_value(SPEC_D707_POST, ValueType.text, None) is None


# ═══ 行内数组：OO 侧新增行 / 旧数据缺键 ═══


def test_new_oo_row_gets_check_items_array_and_debit_amount() -> None:
    """D7-7 区② OO 侧新增一行：客户名 + 勾第 4 项 + 借方金额 ⇒ 建出 5 项数组，其余未勾为 False。"""
    rows, applied, touched = _merge(
        SPEC_D707_POST, [],
        _fv(SPEC_D707_POST, "A", "new1", "甲公司"),
        _fv(SPEC_D707_POST, "M", "new1", True),
        _fv(SPEC_D707_POST, "K", "new1", None),
        _fv(SPEC_D707_POST, "G", "new1", Decimal("300")),
    )
    row = rows["new1"]
    assert row["checkItems"] == [False, False, False, True, False]
    assert row["customerName"] == "甲公司" and row["debitAmount"] == Decimal("300")
    assert "creditAmount" not in row
    assert touched == {"new1"}


def test_existing_array_keeps_other_items_and_length() -> None:
    base = [{SPEC_D307_CURRENT.row_identity_key: "r1", "checkItems": [True, False, True, False, False]}]
    rows, _applied, _t = _merge(SPEC_D307_CURRENT, base, _fv(SPEC_D307_CURRENT, "K", "r1", True))
    assert rows["r1"]["checkItems"] == [True, True, True, False, False]


def test_without_declared_defaults_array_path_fails_closed() -> None:
    """没声明缺省形态的数组路径照旧 fail closed（`json_path` 不擅自建数组）—— 这正是要声明的原因。"""
    bare = dataclasses.replace(SPEC_D707_POST, row_array_defaults=())
    with pytest.raises(JsonPathTypeMismatchError):
        _merge(bare, [], _fv(bare, "A", "n", "乙"), _fv(bare, "J", "n", True))


def test_ensure_row_arrays_never_resizes_an_existing_list() -> None:
    row = {"checkItems": [True, True, True]}
    ensure_row_arrays(SPEC_D707_POST, row, "checkItems/1")
    assert row["checkItems"] == [True, True, True]
    row2: dict = {"checkItems": None}
    ensure_row_arrays(SPEC_D707_POST, row2, "checkItems/0")
    assert row2["checkItems"] == [False] * 5
    row3: dict = {}
    ensure_row_arrays(SPEC_D707_POST, row3, "remark")
    assert row3 == {}
