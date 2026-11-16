"""
test_report_body_export_policy.py

审计报告五个财务占位符按 ExportUnitPolicy 折算
（spec platform-global-display-settings-closure 任务 10 / AC-21）。

判据：
1. **默认 `export_policy=None` 行为逐字节不变**（既有调用方零影响）。
2. 给出 policy 时：五个财务值按 `divisor` 折算 + **数值与标注同源**。
3. 非数字占位文本原样保留（不能因折算中断整份报告）。
4. `divisor == 1`（元）不做量化（`1234.5` 不变成 `1234.50`）。
5. `None` / 空串原样（缺数 ≠ 零）。
6. 五个 placeholder key 必须与 registry 逐值一致（不能漏一个）。
"""

from __future__ import annotations

import inspect
import json
import uuid
from decimal import Decimal

import pytest

from app.services.report_body_service import (
    _UNIT_LABELS,
    _convert_amount_string,
)

#: 五个财务占位符（现读 registry 实证的 key）。
EXPECTED_PLACEHOLDERS = (
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_revenue",
    "net_profit",
)


# ── 1. 签名：policy 可选 ────────────────────────────────

def test_export_policy_param_is_optional() -> None:
    from app.services.report_body_service import ReportBodyService

    sig = inspect.signature(ReportBodyService.fill_placeholders)
    assert "export_policy" in sig.parameters, "fill_placeholders 未接受 export_policy"
    assert sig.parameters["export_policy"].default is None, (
        "export_policy 必须有默认 None（保持既有调用方行为不变）"
    )


# ── 2. 五个 placeholder 与 registry 逐值一致 ─────────────

def test_registry_has_exactly_five_financial_placeholders() -> None:
    from app.services.report_body_service import _load_registry

    fin = _load_registry().get("financial", {})
    assert set(fin) == set(EXPECTED_PLACEHOLDERS), (
        f"财务占位符集合变了：{sorted(fin)}"
    )


def test_each_placeholder_has_report_type_and_row_code() -> None:
    from app.services.report_body_service import _load_registry

    fin = _load_registry().get("financial", {})
    for key, meta in fin.items():
        assert meta.get("report_type"), f"{key} 缺 report_type"
        assert meta.get("row_code"), f"{key} 缺 row_code"


# ── 3. 折算内核 ─────────────────────────────────────────

class TestConvertAmountString:
    def test_divisor_one_is_noop(self) -> None:
        """元口径不做量化：`1234.5` 保持 `1234.5`（不变成 `1234.50`）。"""
        assert _convert_amount_string("1234.5", 1) == "1234.5"
        assert _convert_amount_string("0", 1) == "0"

    def test_wan_division(self) -> None:
        assert _convert_amount_string("12345678.9", 10000) == "1234.57"

    def test_qian_division(self) -> None:
        assert _convert_amount_string("1234567", 1000) == "1234.57"

    def test_round_half_up(self) -> None:
        # 1.005 万分位 → 0.0001005 万元 → 0.00
        assert _convert_amount_string("1.005", 10000) == "0.00"
        # 5000 元 = 0.5 万元
        assert _convert_amount_string("5000", 10000) == "0.50"

    def test_comma_separated_input(self) -> None:
        assert _convert_amount_string("12,345,678.9", 10000) == "1234.57"

    def test_negative_amount(self) -> None:
        assert _convert_amount_string("-5000", 10000) == "-0.50"

    def test_placeholder_text_preserved(self) -> None:
        """非数字（占位文本）原样返回，不中断整份报告。"""
        assert _convert_amount_string("[被审计单位名称]", 10000) == "[被审计单位名称]"

    def test_none_returns_empty_not_zero(self) -> None:
        """缺数是空串，不是 0（零与缺数语义不同）。"""
        assert _convert_amount_string(None, 10000) == ""

    def test_empty_string_returns_empty(self) -> None:
        assert _convert_amount_string("", 10000) == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert _convert_amount_string("   ", 10000) == ""

    def test_nan_inf_preserved(self) -> None:
        assert _convert_amount_string("NaN", 10000) == "NaN"
        assert _convert_amount_string("Infinity", 10000) == "Infinity"


# ── 4. 单位标签闭集 ─────────────────────────────────────

def test_unit_labels_closed_set() -> None:
    assert _UNIT_LABELS == {"yuan": "元", "qian": "千元", "wan": "万元"}


# ── 5. policy 字段名现读实证（防按命名习惯猜）─────────────

def test_export_unit_policy_field_is_unit_not_unit_label() -> None:
    """`ExportUnitPolicy` 的字段是 `unit`，**不是** `unit_label`。

    🔴 变异/tasks 实证：本 spec 曾按命名习惯写 `policy.unit_label` ⇒ AttributeError。
    用例钉住字段名，将来有人改 schema 会立刻红。
    """
    from app.schemas.export_unit_policy import ExportUnitPolicy

    fields = set(ExportUnitPolicy.model_fields)
    assert "unit" in fields, "ExportUnitPolicy 缺 unit 字段"
    assert "unit_label" not in fields, (
        "ExportUnitPolicy 出现了 unit_label —— 若有重命名，先核实全部读取方"
    )
    assert "divisor" in fields


def test_policy_divisor_matches_unit() -> None:
    """三个单位的 divisor 必须与 `UNIT_FACTORS` 逐值一致（1/1000/10000）。"""
    from app.services.ledger_unit_normalization_apply import UNIT_FACTORS

    assert UNIT_FACTORS == {
        "yuan": Decimal("1"),
        "qian": Decimal("1000"),
        "wan": Decimal("10000"),
    }


# ── 6. 「数值与标注同源」的反向断言 ──────────────────────
#
# 🔴 变异实证（2026-11-16）：此前所有用例只测 `_convert_amount_string`（纯函数），
# 从不检查 `fill_placeholders` **有没有把 unit 写进 resolved 条目** ⇒
# 变异「只折算不写标注」全绿存活。
# 「按万元折算但标注写元」比不折算更危险：数值看着合理、单位是错的。


class TestUnitLabelIsWrittenAlongsideValue:
    """折叠后的每个财务条目都必须带 `unit` + `divisor`（与数值同源）。"""

    def _source(self) -> str:
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "app" / "services" / "report_body_service.py"
        return p.read_text(encoding="utf-8")

    def test_entry_sets_unit_when_policy_given(self) -> None:
        src = self._source()
        assert 'entry["unit"] = unit_label' in src, (
            "resolved 条目未写入 unit —— 「按万元折算但标注写元」这类错配无法被发现"
        )

    def test_entry_sets_divisor_when_policy_given(self) -> None:
        src = self._source()
        assert 'entry["divisor"] = str(divisor)' in src, (
            "resolved 条目未写入 divisor —— 下游无法核对折算比例"
        )

    def test_body_level_records_export_unit(self) -> None:
        """body 级也要记一份（下游按 body 读单位时不必逐 section 翻）。"""
        src = self._source()
        assert 'filled["export_unit"]' in src, "body 级未记录 export_unit"

    def test_unit_and_divisor_come_from_same_policy(self) -> None:
        """两者必须取自**同一个** policy 对象（不能一处读 policy、一处写常量）。"""
        src = self._source()
        idx = src.find("if export_policy is not None:")
        assert idx > 0
        seg = src[idx: idx + 700]
        assert "export_policy.divisor" in seg, "divisor 不是从 policy 读的"
        assert "export_policy.unit" in seg, "unit 不是从 policy 读的"

    def test_no_policy_means_no_unit_key(self) -> None:
        """默认（policy=None）时 resolved 条目**不得**出现 unit 键。

        🔴 这是「行为零变化」的精确判据：既有调用方拿到的 dict 逐字节不变。
        """
        src = self._source()
        # `if divisor is not None:` 是唯一写 unit 的入口
        idx = src.find('entry["unit"] = unit_label')
        guard = src.rfind("if divisor is not None:", 0, idx)
        assert guard > 0, "写 unit 的代码没有被 `divisor is not None` 守卫"
