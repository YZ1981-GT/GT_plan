"""Phase 2 测试：binding 从披露表取数。

覆盖：
- note_rows_from_disclosure：标准两字段 / D1 六字段 / 空表 / 多键名兼容
- _read_row_value：业务键 / 别名 / values 数组
- 三个 binding 类的披露表优先路径：NoteDirectBinding / TierAAnchorBinding / BalanceAdjudicationBinding
- 兜底路径：披露表无数据时降级到 TB

spec: note-data-from-disclosure-table Phase 2 Task 13
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.formula_push.bindings.disclosure_source import (
    _read_row_value,
    note_rows_from_disclosure,
)


# ══════════════════════════════════════════════════════════════════════════════
# note_rows_from_disclosure
# ══════════════════════════════════════════════════════════════════════════════


class TestNoteRowsFromDisclosure:
    """核心函数：从 sub_table_data 构建 note_rows。"""

    def test_standard_two_fields(self):
        """标准 end_amount + prior_amount。"""
        sub = {
            "货币资金": [
                {"label": "库存现金", "end_amount": 1000, "prior_amount": 800},
                {"label": "银行存款", "end_amount": 50000, "prior_amount": 45000},
                {"label": "合计", "end_amount": 51000, "prior_amount": 45800, "is_total": True},
            ],
        }
        rows = note_rows_from_disclosure(sub, "货币资金", "E1")
        assert len(rows) == 3
        assert rows[0]["note_label"] == "库存现金"
        assert rows[0]["ending"] == 1000.0
        assert rows[0]["opening"] == 800.0
        assert rows[0]["ending_resolved"] is True
        assert rows[0]["opening_resolved"] is True
        assert rows[0]["is_total"] is False
        assert rows[2]["is_total"] is True

    def test_d1_six_fields(self):
        """D1 六字段变体。"""
        sub = {
            "应收票据分类": [
                {
                    "label": "银行承兑汇票",
                    "end_balance": 100, "end_provision": 10, "end_book_value": 90,
                    "prior_balance": 80, "prior_provision": 8, "prior_book_value": 72,
                },
            ],
        }
        fields = ("end_balance", "end_provision", "end_book_value",
                  "prior_balance", "prior_provision", "prior_book_value")
        rows = note_rows_from_disclosure(sub, "应收票据分类", "D1", fields=fields)
        assert len(rows) == 1
        r = rows[0]
        assert r["end_balance"] == 100.0
        assert r["end_provision"] == 10.0
        assert r["end_book_value"] == 90.0
        assert r["prior_balance"] == 80.0
        assert r["end_balance_resolved"] is True

    def test_empty_table(self):
        """目标表无数据 → 空列表。"""
        assert note_rows_from_disclosure({}, "不存在", "X1") == []

    def test_empty_rows(self):
        """表存在但行列表为空 → 空列表。"""
        assert note_rows_from_disclosure({"T": []}, "T", "X1") == []

    def test_missing_value_unresolved(self):
        """行中缺少值字段 → resolved=False。"""
        sub = {"T": [{"label": "项目A"}]}
        rows = note_rows_from_disclosure(sub, "T", "X1")
        assert len(rows) == 1
        assert rows[0]["ending"] == 0.0
        assert rows[0]["ending_resolved"] is False


# ══════════════════════════════════════════════════════════════════════════════
# _read_row_value 多键名兼容
# ══════════════════════════════════════════════════════════════════════════════


class TestReadRowValue:
    """行值读取：多种键名兼容。"""

    def test_value_key_direct(self):
        """直接命中 value_key。"""
        assert _read_row_value({"ending": 100}, "ending", "end_amount") == 100

    def test_field_name_direct(self):
        """命中 field_name。"""
        assert _read_row_value({"end_amount": 200}, "ending", "end_amount") == 200

    def test_alias_fallback(self):
        """别名兜底：end_balance → ending 的别名。"""
        assert _read_row_value({"end_balance": 300}, "ending", "end_amount") == 300

    def test_values_array_ending(self):
        """F3 格式：values[0] = ending。"""
        assert _read_row_value({"values": [500, 600]}, "ending", "end_amount") == 500

    def test_values_array_opening(self):
        """F3 格式：values[1] = opening。"""
        assert _read_row_value({"values": [500, 600]}, "opening", "prior_amount") == 600

    def test_none_when_nothing_found(self):
        """全部路径都找不到 → None。"""
        assert _read_row_value({}, "ending", "end_amount") is None

    def test_zero_is_valid(self):
        """0 是有效值，不是 None。"""
        assert _read_row_value({"ending": 0}, "ending", "end_amount") == 0


# ══════════════════════════════════════════════════════════════════════════════
# Binding 披露表优先路径
# ══════════════════════════════════════════════════════════════════════════════


def _make_rule(wp_code: str = "F1", table: str = "预付款项", fields=("end_amount", "prior_amount")):
    """构造最小 PushRule mock。"""
    target = MagicMock()
    target.resolve_table = MagicMock(return_value=table)
    target.table = table
    target.fields = fields
    rule = MagicMock()
    rule.target = target
    rule.rule_id = f"{wp_code}.note.main"
    return rule


class TestNoteDirectDisclosurePriority:
    """NoteDirectBinding 优先从披露表取数。"""

    def test_disclosure_data_used_when_available(self):
        from app.services.formula_push.bindings.note_direct import NoteDirectBinding

        b = NoteDirectBinding("F1", ("2001",), "应付账款")
        b._disclosure_sub_table_data = {
            "应付账款": [
                {"label": "供应商A", "end_amount": 100, "prior_amount": 80},
                {"label": "合计", "end_amount": 100, "prior_amount": 80, "is_total": True},
            ],
        }
        b._last_tb_data = {"2001": {"期末余额": 999, "年初余额": 888}}  # TB 有不同的值

        rule = _make_rule("F1", "应付账款")
        rows = b.note_rows({}, "soe", rule)

        # 应该用披露表的值（100/80），不是 TB 的值（999/888）
        assert len(rows) == 2
        assert rows[0]["ending"] == 100.0
        assert rows[0]["opening"] == 80.0

    def test_fallback_to_tb_when_no_disclosure(self):
        from decimal import Decimal
        from app.services.formula_push.bindings.note_direct import NoteDirectBinding

        b = NoteDirectBinding("F1", ("2001",), "应付账款")
        b._disclosure_sub_table_data = None  # 无披露表数据
        b._last_tb_data = {"2001": {"期末余额": Decimal("999"), "年初余额": Decimal("888")}}

        rule = _make_rule("F1", "应付账款")
        rows = b.note_rows({}, "soe", rule)

        # 兜底到 TB
        assert len(rows) == 1
        assert rows[0]["ending"] == 999.0


class TestTierADisclosurePriority:
    """TierAAnchorBinding 优先从披露表取数。"""

    def test_disclosure_data_used(self):
        from app.services.formula_push.bindings.tier_a import TierAAnchorBinding

        b = TierAAnchorBinding("D2", ("1122",))
        b._disclosure_sub_table_data = {
            "按账龄披露": [
                {"label": "1年以内", "end_amount": 500, "prior_amount": 400},
            ],
        }
        b._last_tb_data = {"1122": {"期末余额": 9999}}

        rule = _make_rule("D2", "按账龄披露")
        rows = b.note_rows({}, "soe", rule)

        assert len(rows) == 1
        assert rows[0]["ending"] == 500.0  # 披露表优先，非 TB

    def test_fallback_to_d1_entries_when_no_disclosure(self):
        """D1 无披露表数据时走原 entries 路径。"""
        from app.services.formula_push.bindings.tier_a import TierAAnchorBinding

        b = TierAAnchorBinding("D1", ("1121",), derivations=frozenset({"d1_note_main"}))
        b._disclosure_sub_table_data = None
        b._last_tb_data = None

        rule = _make_rule("D1", "应收票据分类",
                          fields=("end_balance", "end_provision", "end_book_value",
                                  "prior_balance", "prior_provision", "prior_book_value"))
        rule.rule_id = "D1.note.main"
        # entries 中无数据 → 空行
        rows = b.note_rows({}, "soe", rule)
        assert rows == []


class TestBalanceAdjDisclosurePriority:
    """BalanceAdjudicationBinding 优先从披露表取数。"""

    def test_disclosure_data_used(self):
        from app.services.formula_push.bindings.balance_adj import BalanceAdjudicationBinding, AdjudicationSpec

        spec = AdjudicationSpec(
            wp_code="G1", sheet_code="G1-1", account_codes=("1501",),
            has_provision=False,
            fixed_row_keys=("r0",), fixed_row_prefix="",
        )
        b = BalanceAdjudicationBinding(spec)
        b._disclosure_sub_table_data = {
            "交易性金融资产": [
                {"label": "股票", "end_amount": 2000, "prior_amount": 1500},
            ],
        }
        b._last_tb_data = {"1501": {"期末余额": 8888}}

        rule = _make_rule("G1", "交易性金融资产")
        rows = b.note_rows({}, "listed", rule)

        assert len(rows) == 1
        assert rows[0]["ending"] == 2000.0  # 披露表优先
