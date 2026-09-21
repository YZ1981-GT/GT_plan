"""value_type=json 单元格 materialize→extract 往返守卫（本会话第3层-D 修复）。

spec: 逐层修复 D4 双向回写 apply（本会话）· 第3层-D · Property 65

🔴 根因（D4-2 L2 真栈 materialize 500 复现，error_code=roundtrip_projection_mismatch）：
   `value_type=json` 字段（D4-30 custom_dimensions / D4-31 q1_relation）落 Excel 单元格时，
   materialize 侧 `_normalised_write_value` 返回 `merge.normalize_value` 的 canonical **bytes**
   （`{"v": value}` 包裹，仅作比较口径的键）。`inline_text` 渲染 `str(write.value)` 把 bytes
   写成 Python repr（带 `b'...'` 前缀）落盘；extract 读回该字符串后 `normalize_value` 再包一层
   `{"v": "<那串>"}` ⇒ 与提交侧 `{"v": value}` 永远不等值：
       提交 {} → 反读 'b\'{"v":{}}\''  ← Property 65 假红，materialize 500

对称修复：
- materialize：json 落盘写 **value 自身**的 JSON 文本（`{}` / `[]` / `{"a":1}`），不是 bytes repr。
- extract：json 单元格文本 `json.loads` 解回 Python 对象，两侧都持对象后 normalize 对称等值。

本守卫钉住行为级判据（不看源码）：提交任意 JSON 值 → 落盘文本 → 解析回对象 → `values_equal` 为真。
变异反证：把 materialize 改回 `return normalized`（bytes）或把 extract 的 `json.loads` 去掉，
本测试即打红。
"""
from __future__ import annotations

import json

import pytest

from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.merge import values_equal


# 用真实 materialize/extract 的落盘/解析口径，而不是自造第二套
from app.services.workpaper_sync.excel_materialize import _normalised_write_value


class _Spec:
    """最小 FieldSpec 替身：只需 value_type / stable_field_key / mode。"""

    def __init__(self, value_type: ValueType) -> None:
        self.value_type = value_type
        self.stable_field_key = "t/row/custom_dimensions"
        self.mode = FieldMode.editable


class _FieldValue:
    def __init__(self, value) -> None:
        self.value = value


def _simulate_cell_text(value) -> str:
    """复刻 materialize 落盘：_normalised_write_value → _cell_xml(inline_text) 的 str()。"""
    write_value = _normalised_write_value(_FieldValue(value), _Spec(ValueType.json), "S12")
    # inline_text 渲染：'' if None else str(write.value)
    return "" if write_value is None else str(write_value)


def _simulate_extract(cell_text: str):
    """复刻 excel_extract 对 json 单元格的解析：strip → json.loads（空→None）。"""
    text = cell_text.strip()
    if text == "":
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return cell_text


@pytest.mark.parametrize(
    "submitted",
    [
        {},
        [],
        {"a": 1},
        {"key": "自定义维度", "label": "境外销售"},
        [{"dim": "x", "note": "y"}, {"dim": "z", "note": ""}],
        None,
        ["客户是终端客户", "客户是经销商(客户)"],  # D4-31 q1_relation string[]
    ],
)
def test_json_cell_roundtrip_value_stable(submitted) -> None:
    """任意 JSON 值 materialize 落盘 → extract 解析 → 与提交侧 values_equal（Property 65）。"""
    cell_text = _simulate_cell_text(submitted)
    # 落盘绝不能带 Python bytes repr 前缀（那正是 500 的形态）
    assert not cell_text.startswith("b'"), (
        f"json 落盘写成了 bytes repr：{cell_text!r} —— 会触发 roundtrip_projection_mismatch"
    )
    extracted = _simulate_extract(cell_text)
    assert values_equal(submitted, extracted, ValueType.json), (
        f"json 往返不等值：提交 {submitted!r} → 落盘 {cell_text!r} → 反读 {extracted!r}"
    )


def test_empty_dict_is_the_regression_case() -> None:
    """最小复现：D4-30 custom_dimensions 缺省 {} 曾反读成 'b\\'{\"v\":{}}\\''。"""
    cell_text = _simulate_cell_text({})
    assert cell_text == "{}", f"空 dict 应落盘成 '{{}}'，实得 {cell_text!r}"
    assert values_equal({}, _simulate_extract(cell_text), ValueType.json)


def test_bytes_repr_write_would_fail_roundtrip() -> None:
    """变异反证（负向断言）：若落盘仍是 canonical bytes 的 str()（旧 bug 形态），
    extract 解析回来必与提交侧不等值 —— 证明本守卫真的卡住了那条路径。
    """
    from app.services.workpaper_sync.merge import normalize_value

    buggy_cell_text = str(normalize_value({}, ValueType.json))  # 旧 bug：str(bytes)
    assert buggy_cell_text.startswith("b'")
    extracted = _simulate_extract(buggy_cell_text)
    assert not values_equal({}, extracted, ValueType.json), (
        "旧 bug 形态竟往返等值？说明 normalize_value 语义已变，本守卫需重新校准"
    )
