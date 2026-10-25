"""附注子表跨表勾稽校验——纯逻辑测试。

spec: note-sub-table-formula-and-cross-check Phase 0
"""
from __future__ import annotations

import pytest

from app.services.note_check_rules import (
    CheckRule,
    CheckResult,
    _cell_value,
    _find_row_by_label,
    _to_decimal,
    load_all_check_rules,
)
from decimal import Decimal


class TestFindRowByLabel:
    def test_exact_match_list_rows(self):
        rows = [["1年以内", "100"], ["2至3年", "200"], ["合  计", "300"]]
        assert _find_row_by_label(rows, "合  计") == 2

    def test_fuzzy_match_ignores_spaces(self):
        rows = [["合  计", "300"]]
        assert _find_row_by_label(rows, "合计") == 0

    def test_dict_rows(self):
        rows = [{"label": "银行承兑汇票"}, {"label": "合  计"}]
        assert _find_row_by_label(rows, "合计") == 1

    def test_not_found(self):
        rows = [["1年以内", "100"]]
        assert _find_row_by_label(rows, "合计") is None


class TestCellValue:
    def test_list_row(self):
        rows = [["a", "100", "200"], ["b", "300", "400"]]
        assert _cell_value(rows, 0, 1) == "100"
        assert _cell_value(rows, 1, 2) == "400"

    def test_dict_row_values(self):
        rows = [{"label": "x", "values": [10, 20, 30]}]
        assert _cell_value(rows, 0, 1) == 20

    def test_out_of_range(self):
        rows = [["a", "b"]]
        assert _cell_value(rows, 0, 5) is None
        assert _cell_value(rows, 3, 0) is None


class TestToDecimal:
    def test_number(self):
        assert _to_decimal(100) == Decimal("100")

    def test_string(self):
        assert _to_decimal("3.14") == Decimal("3.14")

    def test_none(self):
        assert _to_decimal(None) is None

    def test_empty_string(self):
        assert _to_decimal("") is None

    def test_invalid(self):
        assert _to_decimal("abc") is None


class TestLoadAllCheckRules:
    """验证从真实 JSON 加载 check_rules（写入后才有数据）。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_load_returns_dict(self, std: str):
        """load_all_check_rules 返回 dict，即使没有 check_rules 也不报错。"""
        result = load_all_check_rules(std)
        assert isinstance(result, dict)

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_check_rules_structure(self, std: str):
        """如果有 check_rules，每条必须有 check_id；模式 A 须有 peer_section_id。"""
        all_rules = load_all_check_rules(std)
        for sid, rules in all_rules.items():
            for rule in rules:
                assert rule.check_id, f"{std} {sid}: check_id 为空"
                assert rule.mode in ("cross_table", "column_balance"), f"{std} {sid} {rule.check_id}: 未知 mode {rule.mode}"
                if rule.mode == "cross_table":
                    assert rule.peer_section_id, f"{std} {sid} {rule.check_id}: peer_section_id 为空"
                    assert rule.relation in ("equal",), f"{std} {sid} {rule.check_id}: 未知关系 {rule.relation}"
                elif rule.mode == "column_balance":
                    assert rule.relation in ("column_balance",), f"{std} {sid} {rule.check_id}: 模式B关系应为column_balance"
                    assert all(c >= 0 for c in (rule.opening_col, rule.increase_col, rule.decrease_col, rule.closing_col)), \
                        f"{std} {sid} {rule.check_id}: 模式B列索引不完整"
