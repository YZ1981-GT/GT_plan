# -*- coding: utf-8 -*-
"""F5-P13 前置：`phase5_row_table_sheet` 的 json_path 单源化 + 数组下标往返。

spec: f5-sync-coverage-and-first-canary · Task 0 补-1 / Task 16 · Requirement 4.3
      · Property 13（`months[12]` nested 路径往返）

═══ 这条判据在守什么 ═══

框架层原有**两份** json_path 实现：

| 实现 | 数组下标 | 使用方 |
|---|---|---|
| `json_path.py`（docstring 自称「唯一允许的数组段实现真源」） | ✅ 支持，`FIXED_ARRAY_LENGTHS={"months":12}` | D4 月度矩阵 |
| `phase5_row_table_sheet.py` 内的同名函数 | 🔴 只认 `Mapping` | D1~D7/E1 七家行表 |

后者对 `row["months"]`（list）的行为是**静默错误**：
  * `resolve_json_path(row, "months/0")` → `isinstance(list, Mapping)` False → 返 None ⇒ 投影恒空
  * `set_json_path(row, "months/0", v)` → `nxt` 不是 dict → `cursor["months"] = {}` ⇒ **12 个月数据全丢**

F5-2 的前端 `MonthlyDetailRow.months: number[]` 正是数组 ⇒ 不收敛就没法受管。
本文件钉住「已委托真源」+「dict 语义逐字未变」+「数组 fail-closed 沿用 D4 错误码」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import json_path as shared_json_path  # noqa: E402
from app.services.workpaper_sync import phase5_row_table_sheet as engine  # noqa: E402
from app.services.workpaper_sync.json_path import (  # noqa: E402
    JsonPathArrayIndexOobError,
    JsonPathArrayLengthInvalidError,
)


# ═══════════════════════════════════════════════════════════════════════════
# 组 ①：dict 语义零回归（D1~D7/E1 七家行表依赖「字段缺失 = None」）
# ═══════════════════════════════════════════════════════════════════════════


class TestDictSemanticsUnchanged:
    """🔴 七家 provider 的 store 行常有用户没填的可选字段；投影必须给 None 而不是抛。

    真源 `json_path.resolve_json_path` 在缺段时 fail closed 抛 `JsonPathMissingSegmentError`，
    引擎侧必须把它转成 None —— 否则七家一接就全崩。
    """

    def test_nested_dict_read(self) -> None:
        row = {"agingPrior": {"within1": 5, "y1to2": 0}}
        assert engine.resolve_json_path(row, "agingPrior/within1") == 5
        assert engine.resolve_json_path(row, "agingPrior/y1to2") == 0

    def test_missing_leaf_returns_none(self) -> None:
        row = {"agingPrior": {"within1": 5}}
        assert engine.resolve_json_path(row, "agingPrior/over3") is None

    def test_missing_intermediate_returns_none(self) -> None:
        row = {"agingPrior": {"within1": 5}}
        assert engine.resolve_json_path(row, "agingAudited/within1") is None

    def test_flat_key_read(self) -> None:
        assert engine.resolve_json_path({"endBalance": 12}, "endBalance") == 12
        assert engine.resolve_json_path({"endBalance": 12}, "nope") is None

    def test_scalar_in_path_returns_none(self) -> None:
        """路径穿过标量（形态坏但读路径不该崩）。"""
        assert engine.resolve_json_path({"a": 1}, "a/b") is None

    def test_write_builds_intermediate_dict(self) -> None:
        row: dict = {}
        assert engine.set_json_path(row, "agingPrior/within1", 7) is True
        assert row == {"agingPrior": {"within1": 7}}

    def test_write_same_value_returns_false(self) -> None:
        row = {"agingPrior": {"within1": 7}}
        assert engine.set_json_path(row, "agingPrior/within1", 7) is False

    def test_write_flat_key(self) -> None:
        row: dict = {}
        assert engine.set_json_path(row, "remark", "x") is True
        assert row["remark"] == "x"


# ═══════════════════════════════════════════════════════════════════════════
# 组 ②：数组下标读写（F5-2 `months/0`…`months/11`）
# ═══════════════════════════════════════════════════════════════════════════


class TestArrayIndexRoundtrip:
    def test_read_every_month_slot(self) -> None:
        row = {"months": list(range(12))}
        for i in range(12):
            assert engine.resolve_json_path(row, f"months/{i}") == i

    def test_write_single_slot_keeps_list_type_and_siblings(self) -> None:
        """🔴 F5-P13 核心：改一格只变对应下标元素，其余 11 个不变，且仍是 list。"""
        row = {"months": [0] * 12}
        assert engine.set_json_path(row, "months/3", 42) is True
        assert isinstance(row["months"], list), "months 被替换成了 dict —— 12 个月数据会全丢"
        assert len(row["months"]) == 12
        assert row["months"][3] == 42
        assert [v for i, v in enumerate(row["months"]) if i != 3] == [0] * 11

    def test_write_same_value_returns_false(self) -> None:
        row = {"months": [0] * 12}
        row["months"][5] = 9
        assert engine.set_json_path(row, "months/5", 9) is False

    def test_twelve_writes_accumulate(self) -> None:
        """整行 12 个月依次回写后逐格正确（OO→HTML 合并的真实形态）。"""
        row = {"months": [0] * 12}
        for i in range(12):
            engine.set_json_path(row, f"months/{i}", (i + 1) * 100)
        assert row["months"] == [(i + 1) * 100 for i in range(12)]

    def test_nested_dict_in_array(self) -> None:
        row = {"g": [{"v": 1}, {"v": 2}]}
        assert engine.resolve_json_path(row, "g/1/v") == 2
        assert engine.set_json_path(row, "g/1/v", 9) is True
        assert row["g"][1]["v"] == 9
        assert row["g"][0]["v"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 组 ③：数组错误 fail closed（沿用 D4 既有错误码，不新造）
# ═══════════════════════════════════════════════════════════════════════════


class TestArrayFailClosed:
    """🔴 越界既不静默扩张（造数据）也不静默跳过（丢用户在 OO 的改动）。"""

    def test_read_out_of_bounds_raises(self) -> None:
        row = {"months": [0] * 12}
        with pytest.raises(JsonPathArrayIndexOobError) as exc:
            engine.resolve_json_path(row, "months/12")
        assert exc.value.error_code == "json_path_array_index_oob"

    def test_write_out_of_bounds_raises(self) -> None:
        row = {"months": [0] * 12}
        with pytest.raises(JsonPathArrayIndexOobError):
            engine.set_json_path(row, "months/12", 1)

    def test_wrong_array_length_raises(self) -> None:
        """`FIXED_ARRAY_LENGTHS={"months":12}` —— 长度不符即载荷已坏。"""
        with pytest.raises(JsonPathArrayLengthInvalidError) as exc:
            engine.set_json_path({"months": [0] * 11}, "months/3", 1)
        assert exc.value.error_code == "json_path_array_length_invalid"

    def test_write_index_onto_non_list_raises(self) -> None:
        """下一段是下标而当前段是 dict ⇒ 不得改建成 list，也不得建 dict 掩盖。"""
        with pytest.raises(shared_json_path.JsonPathTypeMismatchError):
            engine.set_json_path({"months": {}}, "months/0", 1)


# ═══════════════════════════════════════════════════════════════════════════
# 组 ④：单源判据 —— 引擎确实委托真源，不是自己又实现了一遍
# ═══════════════════════════════════════════════════════════════════════════


class TestSingleSourceDelegation:
    def test_resolve_delegates_to_shared_module(self, monkeypatch) -> None:
        """把真源换掉，引擎侧必须跟着变 —— 证明不是第二份实现。"""
        calls: list[tuple] = []

        def fake_resolve(root, path, **kwargs):
            calls.append((root, path))
            return "SENTINEL"

        monkeypatch.setattr(shared_json_path, "resolve_json_path", fake_resolve)
        assert engine.resolve_json_path({"a": 1}, "a") == "SENTINEL"
        assert calls == [({"a": 1}, "a")]

    def test_set_delegates_to_shared_module(self, monkeypatch) -> None:
        calls: list[tuple] = []

        def fake_set(root, path, value, **kwargs):
            calls.append((root, path, value))
            return True

        monkeypatch.setattr(shared_json_path, "set_json_path", fake_set)
        assert engine.set_json_path({}, "a", 5) is True
        assert calls == [({}, "a", 5)]

    def test_engine_module_has_no_own_path_walk(self) -> None:
        """AST 判据：引擎的两个函数体内不得再出现自己的路径遍历循环。

        形态特征是 `for ... in json_path.split("/")` / `parts = json_path.split("/")`。
        文本匹配会误命中 docstring 里对旧实现的说明，故走 AST 只看语句。
        """
        import ast
        import inspect

        source_file = Path(inspect.getsourcefile(engine))  # type: ignore[arg-type]
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in {"resolve_json_path", "set_json_path"}:
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "split"
                    and inner.args
                    and isinstance(inner.args[0], ast.Constant)
                    and inner.args[0].value == "/"
                ):
                    offenders.append(f"{node.name} L{inner.lineno}: 自己 split('/') 遍历路径")
        assert not offenders, (
            "引擎又出现了第二份 json_path 实现（应委托 json_path 模块）:\n"
            + "\n".join(offenders)
        )


# ═══════════════════════════════════════════════════════════════════════════
# 组 ⑤：F5-2 契约场景（nested json_key 不得展平）
# ═══════════════════════════════════════════════════════════════════════════


class TestF52MonthlyJsonKeys:
    """裁决 F5-H5：12 个月度列的 `json_key` 用 `months/0`…`months/11` nested 路径，
    不展平成 `month1`…`month12` 顶层键（那要改前端 `updateMonth(id, monthIndex, value)`
    与全部读方）。
    """

    def test_nested_keys_resolve_against_frontend_shape(self) -> None:
        # 前端 StoredMonthlyRow 的真实形态（`months: number[]` 12 元素）
        row = {
            "id": "f5m-uuid",
            "product": "甲",
            "months": [10, 20, 30, 0, 0, 0, 0, 0, 0, 0, 0, 120],
            "currentAje": 5,
            "remark": "",
        }
        keys = [f"months/{i}" for i in range(12)]
        values = [engine.resolve_json_path(row, k) for k in keys]
        assert values == [10, 20, 30, 0, 0, 0, 0, 0, 0, 0, 0, 120]
        # 标量列同一套路径机制
        assert engine.resolve_json_path(row, "currentAje") == 5

    def test_flattened_keys_would_be_empty(self) -> None:
        """反证：展平键在真实前端形态上投影恒空 ⇒ 展平方案不可行。"""
        row = {"months": [10] * 12}
        for i in range(1, 13):
            assert engine.resolve_json_path(row, f"month{i}") is None
